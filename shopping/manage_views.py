"""Kênh quản lý cho Người bán và Quản trị viên: đơn hàng của gian hàng, mã giảm giá, thống kê, đăng ký gian hàng."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import get_role, role_required
from catalog.models import Shop

from . import reports, services
from .models import CancelRequest, Coupon, Order
from .services import OrderError

vendor_only = role_required(Profile.VENDOR)
staff_only = role_required(Profile.VENDOR, Profile.ADMIN)
admin_only = role_required(Profile.ADMIN)


def _my_shop(user):
    return Shop.objects.filter(owner=user).first()


@staff_only
def manage_home(request):
    role = get_role(request.user)
    ctx = {"role": role}
    if role == Profile.VENDOR:
        shop = _my_shop(request.user)
        ctx["shop"] = shop
        if shop:
            services.run_timeouts()
            counts = dict(Order.objects.filter(shop=shop).values_list("status").annotate(n=Count("id")))
            ctx["counts"] = [(label, counts.get(key, 0), key) for key, label in Order.STATUS]
            ctx["pending_cancel"] = CancelRequest.objects.filter(order__shop=shop, result=CancelRequest.PENDING).count()
    else:
        ctx["shops_pending"] = Shop.objects.filter(status=Shop.PENDING).count()
    return render(request, "shopping/manage_home.html", ctx)


# ------------------------------------------------------- đăng ký gian hàng (UC12)
class ShopForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ["name", "description", "pickup_address", "contact", "shop_type"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ("name", "pickup_address", "contact", "shop_type"):
            self.fields[f].required = True


@vendor_only
def shop_register(request):
    if _my_shop(request.user):
        messages.info(request, "Tài khoản Người bán chỉ sở hữu một gian hàng.")
        return redirect("manage_home")
    form = ShopForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        shop = form.save(commit=False)
        shop.owner, shop.status = request.user, Shop.PENDING
        shop.save()
        messages.success(request, "Đã gửi yêu cầu mở gian hàng. Quản trị viên sẽ xét duyệt, trong lúc chờ gian hàng chưa được đăng bán.")
        return redirect("manage_home")
    return render(request, "shopping/shop_register.html", {"form": form})


@vendor_only
def shop_edit(request):
    """Gian hàng bị từ chối xét duyệt: Người bán sửa thông tin và gửi lại (Từ chối -> Chờ duyệt)."""
    shop = _my_shop(request.user)
    if shop is None or shop.status != Shop.REJECTED:
        messages.info(request, "Chỉ gian hàng bị từ chối xét duyệt mới sửa và gửi lại được.")
        return redirect("manage_home")
    form = ShopForm(request.POST or None, instance=shop)
    if request.method == "POST" and form.is_valid():
        shop = form.save(commit=False)
        shop.status, shop.status_reason = Shop.PENDING, ""
        shop.save()
        from .moderation import write_log
        from catalog.models import AdminLog
        write_log(request.user, AdminLog.SHOP, shop.pk, shop.name, "GUI_LAI_XET_DUYET (TU_CHOI->CHO_DUYET)")
        messages.success(request, "Đã gửi lại yêu cầu xét duyệt.")
        return redirect("manage_home")
    return render(request, "shopping/shop_register.html", {"form": form, "resubmit": True})


# ------------------------------------------------------- đơn hàng gian hàng
@vendor_only
def vendor_orders(request):
    shop = _my_shop(request.user)
    if not shop:
        return redirect("manage_home")
    services.run_timeouts()
    status = request.GET.get("trang_thai", "")
    qs = Order.objects.filter(shop=shop).select_related("group").prefetch_related("items", "cancel_requests")
    if status in dict(Order.STATUS):
        qs = qs.filter(status=status)
    orders = list(qs[:100])
    for o in orders:
        o.has_pending = any(r.result == CancelRequest.PENDING for r in o.cancel_requests.all())
    return render(request, "shopping/vendor_orders.html", {"shop": shop, "orders": orders, "status": status, "statuses": Order.STATUS})


@vendor_only
def vendor_order_detail(request, pk):
    services.run_timeouts()
    order = get_object_or_404(Order.objects.select_related("group", "shop"), pk=pk, shop__owner=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "confirm":
                services.update_status(request.user, pk, Order.CONFIRMED)
                messages.success(request, "Đã xác nhận đơn hàng.")
            elif action == "ship":
                services.update_status(request.user, pk, Order.SHIPPING, request.POST.get("carrier"), request.POST.get("tracking"))
                messages.success(request, "Đơn đã chuyển sang Đang giao.")
            elif action == "cancel":
                services.vendor_cancel(request.user, pk, request.POST.get("reason"))
                messages.success(request, "Đã hủy đơn và hoàn trả tồn kho.")
            elif action == "accept_cancel":
                services.vendor_resolve_cancel(request.user, pk, True)
                messages.success(request, "Đã chấp nhận yêu cầu hủy, tồn kho đã được hoàn trả.")
            elif action == "reject_cancel":
                services.vendor_resolve_cancel(request.user, pk, False, request.POST.get("reject_reason"))
                messages.success(request, "Đã từ chối yêu cầu hủy.")
            else:
                raise OrderError("Thao tác không hợp lệ.")
        except OrderError as e:
            messages.error(request, str(e))
        return redirect("vendor_order_detail", pk=pk)
    order.refresh_from_db()
    return render(request, "shopping/vendor_order_detail.html", {
        "o": order, "items": order.items.all(), "logs": order.status_logs.select_related("actor"),
        "pending": order.pending_cancel, "requests": order.cancel_requests.all(),
    })


# --------------------------------------------------------- mã giảm giá (UC14)
class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ["code", "kind", "value", "max_discount", "min_order", "starts", "expires", "max_uses"]
        widgets = {
            "starts": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "expires": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        for f in ("starts", "expires"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M"]
        self.fields["max_discount"].required = False
        self.fields["code"].error_messages["unique"] = "Mã code đã tồn tại, hãy nhập mã khác."


@staff_only
def coupons(request):
    role = get_role(request.user)
    shop = _my_shop(request.user) if role == Profile.VENDOR else None
    if role == Profile.VENDOR:
        qs = Coupon.objects.filter(shop=shop) if shop else Coupon.objects.none()
    else:
        qs = Coupon.objects.select_related("shop")
    can_create = role == Profile.ADMIN or (shop and shop.status == Shop.ACTIVE)
    now = timezone.now()
    form = CouponForm(request.POST or None, instance=Coupon(
        scope=Coupon.GLOBAL if role == Profile.ADMIN else Coupon.SHOP, shop=shop, created_by=request.user,
        starts=now, expires=now + timedelta(days=30)) if request.method != "POST" else
        Coupon(scope=Coupon.GLOBAL if role == Profile.ADMIN else Coupon.SHOP, shop=shop, created_by=request.user))
    if request.method == "POST":
        if not can_create:
            messages.error(request, "Gian hàng cần được Quản trị viên duyệt (Hoạt động) mới tạo được mã giảm giá.")
        elif form.is_valid():
            c = form.save()
            messages.success(request, f"Đã tạo mã {c.code}.")
            return redirect("coupons")
    return render(request, "shopping/coupons.html", {"coupons": qs[:100], "form": form, "role": role, "shop": shop,
                                                     "can_create": can_create, "now": now})


@staff_only
def coupon_detail(request, pk):
    role = get_role(request.user)
    qs = Coupon.objects.select_related("shop")
    c = get_object_or_404(qs if role == Profile.ADMIN else qs.filter(shop__owner=request.user), pk=pk)
    uses = c.uses.select_related("user", "order", "group")
    return render(request, "shopping/coupon_detail.html", {"c": c, "uses": uses})


# ------------------------------------------------------------- thống kê (UC19)
@staff_only
def stats_view(request):
    role = get_role(request.user)
    today = timezone.localdate()
    from datetime import date

    def parse(v, d):
        try:
            return date.fromisoformat(v)
        except (TypeError, ValueError):
            return d

    d_from = parse(request.GET.get("tu_ngay"), today - timedelta(days=29))
    d_to = parse(request.GET.get("den_ngay"), today)
    all_shops = Shop.objects.order_by("name")
    if role == Profile.VENDOR:
        shops = all_shops.filter(owner=request.user)
        shop_filter = ""
    else:
        shop_filter = request.GET.get("gian_hang", "")
        shops = all_shops.filter(pk=shop_filter) if shop_filter.isdigit() else all_shops
    rows, error = [], None
    try:
        rows = reports.stats(d_from, d_to, shops)
    except reports.ReportError as e:
        error = str(e)
    totals = {
        "done": sum(r["done"] for r in rows), "revenue": sum(r["revenue"] for r in rows),
        "cancel_manual": sum(r["cancel_manual"] for r in rows), "cancel_auto": sum(r["cancel_auto"] for r in rows),
        "stock": sum(r["stock"] for r in rows),
    }
    return render(request, "shopping/stats.html", {
        "rows": rows, "totals": totals, "error": error, "d_from": d_from.isoformat(), "d_to": d_to.isoformat(),
        "role": role, "all_shops": all_shops, "shop_filter": shop_filter, "today": today.isoformat(),
        "keywords": reports.popular_keywords() if role == Profile.ADMIN else None,
    })
