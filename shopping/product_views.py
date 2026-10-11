"""Người bán quản lý sản phẩm, danh mục, thẻ phân loại, biến thể, giá và tồn kho (UC13, FR04, BM5, QĐ5)."""
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Min, Q, Sum
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import role_required
from catalog.models import Product, Shop, Variant

from . import services
from .models import OrderItem
from .services import OrderError

vendor_only = role_required(Profile.VENDOR)


def _my_shop(user):
    return Shop.objects.filter(owner=user).first()


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["category", "name", "brand", "tags", "description", "specs", "image", "status"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "specs": forms.Textarea(attrs={"rows": 4}),
                   "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["name"].error_messages["required"] = "Vui lòng nhập tên sản phẩm."
        self.fields["category"].error_messages["required"] = "Sản phẩm bắt buộc thuộc một danh mục."
        self.fields["category"].empty_label = "- Chọn danh mục -"
        if self.instance.pk and self.instance.status == Product.REMOVED:
            # sản phẩm bị Quản trị viên gỡ: Người bán không tự đổi trạng thái hiển thị
            self.fields["status"].disabled = True
        else:
            self.fields["status"].choices = [(Product.VISIBLE, "Hiển thị"), (Product.HIDDEN, "Ẩn")]


class BaseVariantFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        alive = 0
        for f in self.forms:
            cd = getattr(f, "cleaned_data", None)
            if not cd:
                continue
            if cd.get("DELETE"):
                if f.instance.pk and OrderItem.objects.filter(variant_id=f.instance.pk).exists():
                    raise ValidationError(f"Biến thể \"{f.instance.name}\" đã phát sinh đơn hàng nên không xóa được; "
                                          f"hãy đặt tồn kho bằng 0.")
                continue
            alive += 1
        if alive < 1:
            raise ValidationError("Sản phẩm cần ít nhất một biến thể có giá bán (lớn hơn 0) và số lượng tồn (không âm).")


VariantFormSet = inlineformset_factory(Product, Variant, formset=BaseVariantFormSet, fields=["name", "price", "stock"],
                                       extra=1, can_delete=True)


@vendor_only
def product_list(request):
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("trang_thai", "")
    qs = Product.objects.filter(shop=shop).select_related("category") \
        .annotate(total_stock=Sum("variants__stock"), min_price=Min("variants__price"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(tags__icontains=q))
    if status in dict(Product.STATUS):
        qs = qs.filter(status=status)
    return render(request, "shopping/product_list.html", {
        "shop": shop, "products": qs[:200], "q": q, "status": status, "statuses": Product.STATUS})


@vendor_only
def product_form(request, pk=None):
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    if shop.status != Shop.ACTIVE:
        messages.error(request, "Gian hàng chưa được duyệt hoặc đang bị khóa nên chưa được đăng bán sản phẩm.")
        return redirect("manage_home")
    # sản phẩm của gian hàng khác -> 404 (Người bán chỉ thao tác trên dữ liệu gian hàng của mình)
    product = get_object_or_404(Product, pk=pk, shop=shop) if pk else None
    obj = product or Product(shop=shop)
    form = ProductForm(request.POST or None, request.FILES or None, instance=obj)
    fs = VariantFormSet(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid() and fs.is_valid():
        from django.db import transaction
        with transaction.atomic():
            saved = form.save()
            fs.instance = saved
            fs.save()
        messages.success(request, "Đã lưu sản phẩm." if product else "Đã thêm sản phẩm mới.")
        return redirect("product_list")
    return render(request, "shopping/product_form.html", {"form": form, "fs": fs, "product": product, "shop": shop})


@vendor_only
@require_POST
def product_toggle(request, pk):
    shop = _my_shop(request.user)
    p = get_object_or_404(Product, pk=pk, shop=shop) if shop else None
    if p is None:
        return redirect("manage_home")
    if p.status == Product.REMOVED:
        messages.error(request, "Sản phẩm đã bị Quản trị viên gỡ, bạn không tự hiển thị lại được.")
    elif p.status == Product.VISIBLE:
        p.status = Product.HIDDEN
        p.save()
        messages.success(request, f"Đã ẩn \"{p.name}\".")
    else:
        p.status = Product.VISIBLE
        p.save()
        messages.success(request, f"Đã hiển thị \"{p.name}\".")
    return redirect("product_list")


@vendor_only
@require_POST
def product_delete(request, pk):
    try:
        res = services.delete_product(request.user, pk)
        messages.success(request, "Sản phẩm đã phát sinh đơn hàng nên chỉ được ẩn (không xóa hẳn)." if res == "DA_AN"
                         else "Đã xóa sản phẩm.")
    except OrderError as e:
        messages.error(request, str(e))
    return redirect("product_list")
