"""Người bán quản lý sản phẩm, danh mục, thẻ phân loại, biến thể, giá và tồn kho (UC13, FR04, BM5, QĐ5)."""
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Min, Q, Sum
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import role_required
from catalog import images
from catalog.models import Category, Product, ProductImage, Shop, Variant

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

    def clean_image(self):
        img = self.cleaned_data.get("image")
        if isinstance(img, UploadedFile):                 # ảnh mới tải lên: kiểm tra thật + chuẩn hóa
            return images.process_image(img)
        return img

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


PAGE_SIZE = 20
STOCK_FILTERS = [("con_hang", "Còn hàng"), ("sap_het", "Sắp hết"), ("het_hang", "Hết hàng")]


@vendor_only
def product_list(request):
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("trang_thai", "")
    cat = request.GET.get("danh_muc", "")
    stock = request.GET.get("ton_kho", "")
    low = settings.LOW_STOCK_THRESHOLD
    qs = Product.objects.filter(shop=shop).select_related("category") \
        .annotate(total_stock=Sum("variants__stock"), min_price=Min("variants__price"))
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(brand__icontains=q) | Q(tags__icontains=q))
    if status in dict(Product.STATUS):
        qs = qs.filter(status=status)
    if cat.isdigit():
        qs = qs.filter(category_id=cat)
    if stock == "het_hang":
        qs = qs.filter(Q(total_stock=0) | Q(total_stock__isnull=True))
    elif stock == "sap_het":
        qs = qs.filter(total_stock__gt=0, total_stock__lte=low)
    elif stock == "con_hang":
        qs = qs.filter(total_stock__gt=low)
    qs = qs.order_by("-created", "-id")        # truy vấn gộp (GROUP BY) bỏ Meta.ordering: đặt thứ tự tường minh để phân trang ổn định
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("trang"))
    keep = request.GET.copy()
    keep.pop("trang", None)
    return render(request, "shopping/product_list.html", {
        "shop": shop, "products": page.object_list, "page": page, "page_query": keep.urlencode(), "q": q, "status": status,
        "statuses": Product.STATUS, "categories": Category.objects.all(), "cat": cat, "stock": stock,
        "stock_filters": STOCK_FILTERS, "low": low})


def _ints(values):
    return {int(v) for v in values if str(v).isdigit()}


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
    old_cover = product.image.name if product else ""     # phải đọc TRƯỚC khi form gán ảnh mới vào instance
    extras = list(product.extra_images.all()) if product else []
    extra_ids = {e.pk for e in extras}
    form = ProductForm(request.POST or None, request.FILES or None, instance=obj)
    fs = VariantFormSet(request.POST or None, instance=obj)
    gallery_ok, gallery_errors, del_ids, cover_from = [], [], set(), None
    if request.method == "POST":
        gallery_ok, gallery_errors = images.validate_many(request.FILES.getlist("gallery"))
        del_ids = _ints(request.POST.getlist("del_img")) & extra_ids
        cf = _ints([request.POST.get("cover_from", "")]) & (extra_ids - del_ids)
        cover_from = next(iter(cf), None)
    forms_ok = form.is_valid() & fs.is_valid() if request.method == "POST" else False
    if forms_ok:
        total = bool(form.cleaned_data.get("image")) + len(extras) - len(del_ids) + len(gallery_ok)
        if total > settings.PRODUCT_IMAGE_MAX_COUNT:
            gallery_errors.append(f"Mỗi sản phẩm tối đa {settings.PRODUCT_IMAGE_MAX_COUNT} ảnh (gồm ảnh bìa); "
                                  f"hiện sẽ có {total} ảnh. Hãy xóa bớt ảnh cũ hoặc chọn ít ảnh hơn.")
    if forms_ok and not gallery_errors:
        with transaction.atomic():
            saved = form.save()
            fs.instance = saved
            fs.save()
            for e in extras:
                if e.pk in del_ids:
                    e.delete()                              # tín hiệu post_delete xóa file sau khi commit
            if cover_from:                                  # đặt một ảnh phụ làm ảnh bìa: đổi chỗ với ảnh bìa hiện tại
                e = ProductImage.objects.get(pk=cover_from, product=saved)
                prev = saved.image.name
                saved.image.name = e.image.name
                saved.save(update_fields=["image"])
                if prev:
                    e.image.name = prev
                    e.save(update_fields=["image"])
                else:
                    e.image = ""
                    e.delete()
            pos = (ProductImage.objects.filter(product=saved).order_by("-position").values_list("position", flat=True).first() or 0)
            for cf in gallery_ok:
                pos += 1
                ProductImage.objects.create(product=saved, image=cf, position=pos)
            in_use = {saved.image.name, *ProductImage.objects.filter(product=saved).values_list("image", flat=True)}
            if old_cover and old_cover not in in_use:       # ảnh bìa cũ đã bị thay hoặc xóa
                images.delete_file_later(saved.image.storage, old_cover)
        messages.success(request, "Đã lưu sản phẩm." if product else "Đã thêm sản phẩm mới.")
        return redirect("product_list")
    return render(request, "shopping/product_form.html", {
        "form": form, "fs": fs, "product": product, "shop": shop, "extras": extras, "gallery_errors": gallery_errors,
        "max_images": settings.PRODUCT_IMAGE_MAX_COUNT, "max_mb": settings.PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)})


# ------------------------------------------------ kho nhanh: giá và tồn theo biến thể
INV_PAGE = 30


@vendor_only
def inventory(request):
    """Cập nhật nhanh giá và tồn kho nhiều biến thể trong một lần lưu.
    Tồn kho áp dụng theo CHÊNH LỆCH so với số đang hiển thị: nếu trong lúc bạn sửa có khách đặt hàng làm tồn thay đổi,
    số khách đã mua không bị ghi đè."""
    shop = _my_shop(request.user)
    if shop is None:
        return redirect("manage_home")
    low = settings.LOW_STOCK_THRESHOLD
    flt = request.GET.get("loc", "")
    q = request.GET.get("q", "").strip()
    qs = Variant.objects.filter(product__shop=shop).select_related("product__category").order_by("product__name", "name", "id")
    if q:
        qs = qs.filter(Q(product__name__icontains=q) | Q(name__icontains=q))
    if flt == "het":
        qs = qs.filter(stock=0)
    elif flt == "sap_het":
        qs = qs.filter(stock__gt=0, stock__lte=low)
    if request.method == "POST":
        ids = _ints(request.POST.getlist("ids"))
        errors, changes = [], []
        with transaction.atomic():
            rows = {v.pk: v for v in Variant.objects.select_for_update().select_related("product")
                    .filter(pk__in=ids, product__shop=shop)}
            for vid in ids:
                v = rows.get(vid)
                if v is None:
                    continue
                label = f"{v.product.name} - {v.name}"
                try:
                    price, typed, orig = (int(request.POST[f"price_{vid}"]), int(request.POST[f"stock_{vid}"]),
                                          int(request.POST[f"orig_stock_{vid}"]))
                except (KeyError, ValueError):
                    errors.append(f"{label}: giá và tồn kho phải là số nguyên.")
                    continue
                if price <= 0 or price > 1_000_000_000:
                    errors.append(f"{label}: giá bán phải lớn hơn 0.")
                    continue
                new_stock = typed if v.stock == orig else v.stock + (typed - orig)
                if typed < 0 or new_stock < 0:
                    errors.append(f"{label}: số lượng tồn không hợp lệ (tồn hiện tại đã đổi do có đơn mới, hãy tải lại trang).")
                    continue
                if price != int(v.price) or new_stock != v.stock:
                    changes.append((v, price, new_stock))
            if errors:
                transaction.set_rollback(True)
            else:
                for v, price, new_stock in changes:
                    v.price, v.stock = price, new_stock
                    v.save(update_fields=["price", "stock"])
        if errors:
            for e in errors[:10]:
                messages.error(request, e)
        else:
            messages.success(request, f"Đã cập nhật {len(changes)} biến thể." if changes else "Không có thay đổi nào.")
        return redirect(request.get_full_path())
    page = Paginator(qs, INV_PAGE).get_page(request.GET.get("trang"))
    keep = request.GET.copy()
    keep.pop("trang", None)
    return render(request, "shopping/inventory.html", {
        "shop": shop, "variants": page.object_list, "page": page, "page_query": keep.urlencode(), "loc": flt, "q": q, "low": low,
        "n_out": Variant.objects.filter(product__shop=shop, stock=0).count(),
        "n_low": Variant.objects.filter(product__shop=shop, stock__gt=0, stock__lte=low).count()})


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
