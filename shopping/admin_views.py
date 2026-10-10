"""Giao diện Quản trị viên: xét duyệt / khóa gian hàng (UC16, UC17), gỡ / khôi phục sản phẩm (UC17),
từ điển từ khóa gợi ý (UC18), hoàn tiền mô phỏng, nhật ký quản trị (NFR09)."""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import role_required
from catalog.models import AdminLog, Keyword, Product, Shop

from . import moderation, services
from .models import Order, PaymentTransaction
from .services import OrderError

admin_only = role_required(Profile.ADMIN)

SHOP_ACTIONS = {"approve": "HOAT_DONG", "reject": "TU_CHOI", "lock": "BI_KHOA", "unlock": "HOAT_DONG"}


@admin_only
def shops_review(request):
    if request.method == "POST":
        new = SHOP_ACTIONS.get(request.POST.get("action"))
        try:
            if not new:
                raise OrderError("Thao tác không hợp lệ.")
            moderation.set_shop_status(request.user, request.POST.get("shop"), new, request.POST.get("reason"))
            messages.success(request, "Đã cập nhật trạng thái gian hàng và thông báo cho Người bán.")
        except OrderError as e:
            messages.error(request, str(e))
        return redirect(request.get_full_path())
    status = request.GET.get("trang_thai", Shop.PENDING)
    qs = Shop.objects.select_related("owner").order_by("-created")
    if status in dict(Shop.STATUS):
        qs = qs.filter(status=status)
    return render(request, "shopping/admin_shops.html", {"shops": qs[:100], "status": status, "statuses": Shop.STATUS})


@admin_only
def products_review(request):
    if request.method == "POST":
        try:
            pid, reason = request.POST.get("product"), request.POST.get("reason")
            if request.POST.get("action") == "remove":
                moderation.remove_product(request.user, pid, reason)
                messages.success(request, "Đã gỡ sản phẩm và thông báo cho Người bán.")
            elif request.POST.get("action") == "restore":
                moderation.restore_product(request.user, pid, reason)
                messages.success(request, "Đã khôi phục sản phẩm (trạng thái Ẩn).")
            else:
                raise OrderError("Thao tác không hợp lệ.")
        except OrderError as e:
            messages.error(request, str(e))
        return redirect(request.get_full_path())
    q = request.GET.get("q", "").strip()
    status = request.GET.get("trang_thai", "")
    qs = Product.objects.select_related("shop", "category")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(shop__name__icontains=q) | Q(brand__icontains=q))
    if status in dict(Product.STATUS):
        qs = qs.filter(status=status)
    return render(request, "shopping/admin_products.html", {
        "products": qs.order_by("-created")[:100], "q": q, "status": status, "statuses": Product.STATUS})


@admin_only
def keywords_review(request):
    if request.method == "POST":
        try:
            show = request.POST.get("action") == "show"
            moderation.set_keyword_visibility(request.user, request.POST.get("keyword"), show, request.POST.get("reason"))
            messages.success(request, "Đã hiện lại từ khóa." if show else "Đã ẩn từ khóa khỏi gợi ý (người dùng vẫn tìm kiếm bình thường).")
        except OrderError as e:
            messages.error(request, str(e))
        return redirect(request.get_full_path())
    q = request.GET.get("q", "").strip()
    qs = Keyword.objects.all()
    if q:
        qs = qs.filter(phrase__icontains=q)
    return render(request, "shopping/admin_keywords.html", {"keywords": qs[:100], "q": q})


@admin_only
def refunds(request):
    """Hoàn tiền mô phỏng trong Sandbox: Chờ hoàn tiền -> Đã hoàn tiền."""
    if request.method == "POST":
        try:
            if request.POST.get("kind") == "txn":
                services.complete_late_refund(request.POST.get("id"), request.user)
            else:
                services.complete_refund(request.POST.get("id"), request.user)
            messages.success(request, "Đã hoàn tiền (mô phỏng Sandbox).")
        except OrderError as e:
            messages.error(request, str(e))
        return redirect("refunds")
    return render(request, "shopping/admin_refunds.html", {
        "orders": Order.objects.filter(payment_status=Order.REFUND_WAIT).select_related("shop", "group"),
        "txns": PaymentTransaction.objects.filter(refund_status=PaymentTransaction.REFUND_WAIT).select_related("group")})


@admin_only
def admin_logs(request):
    kind = request.GET.get("loai", "")
    qs = AdminLog.objects.select_related("actor")
    if kind in dict(AdminLog.TARGETS):
        qs = qs.filter(target_type=kind)
    return render(request, "shopping/admin_logs.html", {"logs": qs[:200], "kind": kind, "kinds": AdminLog.TARGETS})
