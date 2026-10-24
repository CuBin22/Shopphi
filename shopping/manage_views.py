"""Kênh quản lý cho Người bán và Quản trị viên: đơn hàng của gian hàng, mã giảm giá, thống kê, đăng ký gian hàng."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import get_role, role_required
from catalog.models import Product, Shop, Variant

from . import reports, services
from .models import CancelRequest, Coupon, Order, OrderItem
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
            ctx["pipeline_total"] = sum(n for _, n, _ in ctx["counts"])
            ctx["pipeline"] = [(label, n, key, round(n * 100 / ctx["pipeline_total"], 2) if ctx["pipeline_total"] else 0)
                               for label, n, key in ctx["counts"]]
            ctx["pending_cancel"] = CancelRequest.objects.filter(order__shop=shop, result=CancelRequest.PENDING).count()
            ctx.update(_vendor_kpis(shop))
            today = timezone.localdate()
            ctx["chart"] = reports.chart_data(reports.daily_revenue(today - timedelta(days=29), today, shop))
            top = ctx["top_products"]
            peak = max((t["qty"] for t in top), default=0)
            for t in top:
                t["pct"] = round(t["qty"] * 100 / peak, 2) if peak else 0
    else:
        ctx.update(_admin_overview())
    return render(request, "shopping/manage_home.html", ctx)


def _admin_overview():
    """Số liệu tổng quan toàn sàn cho bảng điều khiển Quản trị viên (30 ngày gần nhất)."""
    from catalog.models import AdminLog
    from .models import PaymentTransaction
    today = timezone.localdate()
    start = today - timedelta(days=29)
    shops = list(Shop.objects.order_by("name"))
    rows = reports.stats(start, today, shops)
    ranked = sorted((r for r in rows if r["revenue"] or r["done"]), key=lambda r: -r["revenue"])[:5]
    peak = max((r["revenue"] for r in ranked), default=0)
    for r in ranked:
        r["pct"] = round(r["revenue"] * 100 / peak, 2) if peak else 0
    status_counts = dict(Shop.objects.values_list("status").annotate(n=Count("id")))
    return {
        "shops_pending": status_counts.get(Shop.PENDING, 0),
        "shops_active": status_counts.get(Shop.ACTIVE, 0),
        "shops_locked": status_counts.get(Shop.LOCKED, 0),
        "refunds_waiting": (Order.objects.filter(payment_status=Order.REFUND_WAIT).count()
                            + PaymentTransaction.objects.filter(refund_status=PaymentTransaction.REFUND_WAIT).count()),
        "n_products_visible": Product.objects.filter(status=Product.VISIBLE, shop__status=Shop.ACTIVE).count(),
        "month_revenue": sum(r["revenue"] for r in rows),
        "month_done": sum(r["done"] for r in rows),
        "month_cancel": sum(r["cancel_manual"] + r["cancel_auto"] for r in rows),
        "top_shops": ranked,
        "chart": reports.chart_data(reports.daily_revenue(start, today)),
        "recent_logs": list(AdminLog.objects.select_related("actor")[:6]),
    }


def _vendor_kpis(shop):
    """Số liệu nhanh cho bảng điều khiển Người bán."""
    today = timezone.localdate()
    low = settings.LOW_STOCK_THRESHOLD
    day = reports.stats(today, today, [shop])[0]
    month = reports.stats(today - timedelta(days=29), today, [shop])[0]
    variants = Variant.objects.filter(product__shop=shop)
    top = (OrderItem.objects.filter(order__shop=shop, order__status=Order.DONE, order__created__gte=timezone.now() - timedelta(days=30))
           .values("variant__product_id", "product_name").annotate(qty=Sum("qty")).order_by("-qty")[:5])
    return {
        "kpi_today": day, "kpi_month": month,
        "n_products": Product.objects.filter(shop=shop).count(),
        "n_visible": Product.objects.filter(shop=shop, status=Product.VISIBLE).count(),
        "n_out": variants.filter(stock=0).count(),
        "n_low": variants.filter(stock__gt=0, stock__lte=low).count(),
        "waiting_old": Order.objects.filter(shop=shop, status=Order.PENDING, payment_status__in=[Order.UNPAID, Order.PAID],
                                            created__lte=timezone.now() - timedelta(hours=24)).count(),
        "top_products": list(top), "low": low,
    }


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
    pay = request.GET.get("thanh_toan", "")
    q = request.GET.get("q", "").strip()
    d_from, d_to = request.GET.get("tu_ngay", ""), request.GET.get("den_ngay", "")
    qs = Order.objects.filter(shop=shop).select_related("group").prefetch_related("items", "cancel_requests")
    if status in dict(Order.STATUS):
        qs = qs.filter(status=status)
    if pay in dict(Order.PAY_STATUS):
        qs = qs.filter(payment_status=pay)
    if q:
        cond = (Q(group__recipient_name__icontains=q) | Q(group__recipient_phone__icontains=q) | Q(tracking_code__icontains=q))
        if q.lstrip("#").isdigit():
            cond |= Q(pk=int(q.lstrip("#")))
        qs = qs.filter(cond)
    from datetime import date
    for val, lookup in ((d_from, "created__date__gte"), (d_to, "created__date__lte")):
        try:
            qs = qs.filter(**{lookup: date.fromisoformat(val)}) if val else qs
        except ValueError:
            pass
    page = Paginator(qs, 20).get_page(request.GET.get("trang"))
    orders = list(page.object_list)
    for o in orders:
        o.has_pending = any(r.result == CancelRequest.PENDING for r in o.cancel_requests.all())
    keep = request.GET.copy()
    keep.pop("trang", None)
    return render(request, "shopping/vendor_orders.html", {
        "shop": shop, "orders": orders, "page": page, "page_query": keep.urlencode(), "status": status, "statuses": Order.STATUS,
        "pay": pay, "pay_statuses": Order.PAY_STATUS, "q": q, "d_from": d_from, "d_to": d_to})


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
        "o": order, "items": order.items.select_related("variant__product__category"), "logs": order.status_logs.select_related("actor"),
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
    can_manage = (role == Profile.ADMIN and c.scope == Coupon.GLOBAL) or (role == Profile.VENDOR and c.shop_id and c.shop.owner_id == request.user.pk)
    return render(request, "shopping/coupon_detail.html", {"c": c, "uses": uses, "can_manage": can_manage})


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
    chart = None
    if not error:
        one = shops.first() if role == Profile.VENDOR or shop_filter.isdigit() else None
        chart = reports.chart_data(reports.daily_revenue(d_from, d_to, one))
        peak = max((r["revenue"] for r in rows), default=0)
        for r in rows:
            r["pct"] = round(r["revenue"] * 100 / peak, 2) if peak else 0
    return render(request, "shopping/stats.html", {
        "chart": chart, "rows": rows, "totals": totals, "error": error, "d_from": d_from.isoformat(), "d_to": d_to.isoformat(),
        "role": role, "all_shops": all_shops, "shop_filter": shop_filter, "today": today.isoformat(),
        "keywords": reports.popular_keywords() if role == Profile.ADMIN else None,
    })
