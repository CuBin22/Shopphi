"""Nghiệp vụ bổ sung cho Người bán: đánh giá sản phẩm, thông tin gian hàng, phiếu giao vận, quản lý vòng đời mã giảm giá.

Quy tắc mã giảm giá (đóng Open Issue UC14 #1):
  * chưa có lượt dùng: sửa mọi thông tin, hoặc xóa hẳn;
  * đã có lượt dùng: chỉ được gia hạn ngày hết hạn và tăng số lượt tối đa, không đổi mã/loại/giá trị/đơn tối thiểu (khách đã dựa vào);
    không xóa; muốn dừng thì Tạm ngưng (mã đang tạm ngưng không áp dụng được cho đơn mới, đơn đã đặt không bị ảnh hưởng).
"""
from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import get_role, role_required
from catalog.models import Product, Shop

from .manage_views import CouponForm, _my_shop, staff_only, vendor_only
from .models import Coupon, Order, Review


# ------------------------------------------------------------------ đánh giá sản phẩm
@vendor_only
def vendor_reviews(request):
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    qs = Review.objects.filter(product__shop=shop).select_related("user", "product")
    stars = request.GET.get("sao", "")
    pid = request.GET.get("san_pham", "")
    if stars in {"1", "2", "3", "4", "5"}:
        qs = qs.filter(rating=int(stars))
    if pid.isdigit():
        qs = qs.filter(product_id=pid)
    all_reviews = Review.objects.filter(product__shop=shop)
    dist = dict(all_reviews.values_list("rating").annotate(n=Count("id")))
    page = Paginator(qs, 20).get_page(request.GET.get("trang"))
    keep = request.GET.copy()
    keep.pop("trang", None)
    return render(request, "shopping/vendor_reviews.html", {
        "shop": shop, "page": page, "reviews": page.object_list, "page_query": keep.urlencode(), "stars": stars, "pid": pid,
        "avg": all_reviews.aggregate(a=Avg("rating"))["a"], "total": all_reviews.count(),
        "dist": [(n, dist.get(n, 0)) for n in (5, 4, 3, 2, 1)],
        "products": Product.objects.filter(shop=shop, reviews__isnull=False).distinct().order_by("name")})


# ------------------------------------------------------------- thông tin gian hàng
class ShopInfoForm(forms.ModelForm):
    class Meta:
        model = Shop
        fields = ["description", "pickup_address", "contact"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["pickup_address"].required = True
        self.fields["contact"].required = True


@vendor_only
def shop_info(request):
    """Người bán cập nhật mô tả, địa chỉ lấy hàng, thông tin liên hệ khi gian hàng đang vận hành. Tên và loại hình
    đã được Quản trị viên duyệt nên không tự đổi."""
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    if shop.status == Shop.REJECTED:
        return redirect("shop_edit")
    form = ShopInfoForm(request.POST or None, instance=shop)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã cập nhật thông tin gian hàng.")
        return redirect("manage_home")
    return render(request, "shopping/shop_info.html", {"form": form, "shop": shop})


# ------------------------------------------------------------------- phiếu giao vận
@vendor_only
def packing_slip(request, pk):
    """Phiếu giao vận để in (QĐ10): chỉ tạo khi đơn Đã xác nhận (hoặc đang giao, để in lại); tồn kho đã trừ từ lúc đặt hàng."""
    order = get_object_or_404(Order.objects.select_related("group", "shop"), pk=pk, shop__owner=request.user)
    if order.status not in (Order.CONFIRMED, Order.SHIPPING):
        messages.error(request, "Chỉ tạo phiếu giao vận cho đơn đã xác nhận hoặc đang giao.")
        return redirect("vendor_order_detail", pk=pk)
    cod_due = order.total if (order.group.payment_method == "COD" and order.payment_status != Order.PAID) else 0
    return render(request, "shopping/packing_slip.html", {"o": order, "items": order.items.all(), "cod_due": cod_due})


# ------------------------------------------------------------ vòng đời mã giảm giá
def _coupon_for(request, pk):
    role = get_role(request.user)
    qs = Coupon.objects.select_related("shop")
    if role == Profile.ADMIN:
        return get_object_or_404(qs.filter(scope=Coupon.GLOBAL), pk=pk)       # Quản trị viên quản lý mã toàn sàn
    return get_object_or_404(qs.filter(shop__owner=request.user), pk=pk)


@staff_only
def coupon_edit(request, pk):
    c = _coupon_for(request, pk)
    used = c.used_count > 0 or c.uses.exists()
    form = CouponForm(request.POST or None, instance=c)
    if used:
        for name in ("code", "kind", "value", "max_discount", "min_order", "starts"):
            form.fields[name].disabled = True
    if request.method == "POST" and form.is_valid():
        if used and form.cleaned_data["max_uses"] < c.used_count:
            form.add_error("max_uses", f"Số lượt tối đa không được nhỏ hơn số lượt đã dùng ({c.used_count}).")
        else:
            form.save()
            messages.success(request, f"Đã cập nhật mã {c.code}.")
            return redirect("coupon_detail", pk=c.pk)
    return render(request, "shopping/coupon_form.html", {"form": form, "c": c, "used": used})


@staff_only
@require_POST
def coupon_toggle(request, pk):
    c = _coupon_for(request, pk)
    c.is_active = not c.is_active
    c.save(update_fields=["is_active"])
    messages.success(request, f"Đã {'bật lại' if c.is_active else 'tạm ngưng'} mã {c.code}.")
    return redirect(request.POST.get("next") or "coupons")


@staff_only
@require_POST
def coupon_delete(request, pk):
    c = _coupon_for(request, pk)
    if c.used_count > 0 or c.uses.exists():
        messages.error(request, f"Mã {c.code} đã có lượt sử dụng nên không xóa được; hãy dùng Tạm ngưng.")
        return redirect("coupon_detail", pk=c.pk)
    try:
        code = c.code
        c.delete()
    except ProtectedError:
        messages.error(request, f"Mã {c.code} đã gắn với đơn hàng nên không xóa được; hãy dùng Tạm ngưng.")
        return redirect("coupon_detail", pk=c.pk)
    messages.success(request, f"Đã xóa mã {code}.")
    return redirect("coupons")
