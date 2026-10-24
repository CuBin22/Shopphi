from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from .text import chuan_hoa, khong_dau


class Category(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField("Tên danh mục", max_length=60)
    order = models.PositiveSmallIntegerField("Thứ tự", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Danh mục"
        verbose_name_plural = "Danh mục"

    def __str__(self):
        return self.name


class Shop(models.Model):
    PENDING, ACTIVE, REJECTED, LOCKED = "CHO_DUYET", "HOAT_DONG", "TU_CHOI", "BI_KHOA"
    STATUS = [
        (PENDING, "Chờ duyệt"),
        (ACTIVE, "Hoạt động"),
        (REJECTED, "Từ chối xét duyệt"),
        (LOCKED, "Bị khóa"),
    ]
    SHOP_TYPES = [("CA_NHAN", "Cá nhân"), ("DOANH_NGHIEP", "Doanh nghiệp")]
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name="shop", verbose_name="Chủ gian hàng")
    name = models.CharField("Tên gian hàng", max_length=120, unique=True)
    description = models.TextField("Mô tả", blank=True)
    pickup_address = models.CharField("Địa chỉ lấy hàng", max_length=255, blank=True)
    contact = models.CharField("Số điện thoại / Email liên hệ", max_length=120, blank=True)
    shop_type = models.CharField("Loại hình", max_length=14, choices=SHOP_TYPES, default="CA_NHAN")
    status = models.CharField("Trạng thái", max_length=12, choices=STATUS, default=PENDING)
    status_reason = models.CharField("Lý do khóa / từ chối", max_length=255, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gian hàng"
        verbose_name_plural = "Gian hàng"

    def __str__(self):
        return self.name

    def clean(self):
        if self.status in (self.LOCKED, self.REJECTED) and not self.status_reason.strip():
            raise ValidationError({"status_reason": "Bắt buộc ghi lý do khi khóa hoặc từ chối gian hàng."})


class ProductQuerySet(models.QuerySet):
    def sellable(self):
        """Sản phẩm đang hiển thị của gian hàng đang hoạt động."""
        return self.filter(status=Product.VISIBLE, shop__status=Shop.ACTIVE)


class Product(models.Model):
    VISIBLE, HIDDEN, REMOVED = "HIEN_THI", "AN", "BI_GO"
    STATUS = [(VISIBLE, "Hiển thị"), (HIDDEN, "Ẩn"), (REMOVED, "Bị gỡ")]

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="products", verbose_name="Gian hàng")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="Danh mục")
    name = models.CharField("Tên sản phẩm", max_length=200)
    slug = models.SlugField(max_length=255, blank=True, db_index=True)
    brand = models.CharField("Thương hiệu", max_length=80, blank=True)
    tags = models.CharField("Thẻ phân loại (cách nhau bằng dấu phẩy)", max_length=255, blank=True)
    description = models.TextField("Mô tả", blank=True)
    image = models.ImageField("Ảnh sản phẩm", upload_to="products/", blank=True)
    specs = models.TextField("Thông số kỹ thuật (mỗi dòng: Tên: Giá trị)", blank=True)
    status = models.CharField("Trạng thái hiển thị", max_length=10, choices=STATUS, default=VISIBLE)
    removal_reason = models.CharField("Lý do gỡ", max_length=255, blank=True)
    search_text = models.TextField(editable=False, default="")
    created = models.DateTimeField(auto_now_add=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Sản phẩm"
        verbose_name_plural = "Sản phẩm"

    def __str__(self):
        return self.name

    def clean(self):
        if self.status == self.REMOVED and not self.removal_reason.strip():
            raise ValidationError({"removal_reason": "Bắt buộc ghi lý do khi gỡ sản phẩm."})

    def save(self, *args, **kwargs):
        self.search_text = khong_dau(f"{self.name} {self.brand} {self.tags} {self.category.name}")
        super().save(*args, **kwargs)
        if not self.slug:
            self.slug = f"{slugify(khong_dau(self.name))}-{self.pk}"
            super().save(update_fields=["slug"])

    def get_absolute_url(self):
        return reverse("product", args=[self.slug])

    def gallery(self):
        """Danh sách ảnh để hiển thị: ảnh bìa trước, rồi các ảnh phụ theo thứ tự. Mỗi phần tử có thuộc tính url."""
        items = [self.image] if self.image else []
        items += [g.image for g in self.extra_images.all() if g.image]
        return items

    def image_count(self):
        return (1 if self.image else 0) + self.extra_images.count()

    def spec_rows(self):
        rows = []
        for line in self.specs.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                rows.append((k.strip(), v.strip()))
        return rows

    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name="Sản phẩm")
    name = models.CharField("Biến thể", max_length=80, default="Mặc định")
    price = models.DecimalField("Giá bán (đã gồm VAT)", max_digits=12, decimal_places=0,
                                validators=[MinValueValidator(1)])
    stock = models.PositiveIntegerField("Tồn kho", default=0)

    class Meta:
        ordering = ["id"]
        verbose_name = "Biến thể"
        verbose_name_plural = "Biến thể"

    def __str__(self):
        return f"{self.product.name} - {self.name}"


class BehaviorLog(models.Model):
    SEARCH, VIEW, CLICK, ADD, PURCHASE = "SEARCH", "VIEW", "CLICK", "ADD_TO_CART", "PURCHASE"
    TYPES = [(SEARCH, "Tìm kiếm"), (VIEW, "Xem chi tiết"), (CLICK, "Nhấp chọn"),
             (ADD, "Thêm vào giỏ"), (PURCHASE, "Mua hàng")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="+")
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    type = models.CharField(max_length=12, choices=TYPES, db_index=True)
    keyword = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=30, blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Log hành vi"
        verbose_name_plural = "Log hành vi"


class Keyword(models.Model):
    phrase = models.CharField("Cụm từ khóa", max_length=120)
    plain = models.CharField("Không dấu", max_length=120, unique=True, editable=False)
    frequency = models.PositiveIntegerField("Tần suất tìm kiếm", default=0)
    match_count = models.PositiveIntegerField("Số sản phẩm khớp", default=0, editable=False)
    visible = models.BooleanField("Hiện trong gợi ý", default=True)
    hidden_reason = models.CharField("Lý do ẩn", max_length=255, blank=True)
    hidden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name="+", editable=False)

    class Meta:
        ordering = ["-frequency", "phrase"]
        verbose_name = "Từ khóa gợi ý"
        verbose_name_plural = "Từ điển từ khóa gợi ý"

    def __str__(self):
        return self.phrase

    def clean(self):
        if not self.visible and not self.hidden_reason.strip():
            raise ValidationError({"hidden_reason": "Cần nhập lý do khi ẩn từ khóa."})

    def save(self, *args, **kwargs):
        self.phrase = chuan_hoa(self.phrase)
        self.plain = khong_dau(self.phrase)
        super().save(*args, **kwargs)


class AdminLog(models.Model):
    """Nhật ký quản trị (NFR09): duyệt/khóa gian hàng, gỡ/khôi phục sản phẩm, ẩn/hiện từ khóa."""
    SHOP, PRODUCT, KEYWORD = "GIAN_HANG", "SAN_PHAM", "TU_KHOA"
    TARGETS = [(SHOP, "Gian hàng"), (PRODUCT, "Sản phẩm"), (KEYWORD, "Từ khóa")]

    at = models.DateTimeField("Thời điểm", auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                              related_name="+", verbose_name="Người thực hiện")
    target_type = models.CharField("Loại đối tượng", max_length=10, choices=TARGETS)
    target_id = models.PositiveIntegerField("Mã đối tượng")
    target_label = models.CharField("Đối tượng", max_length=200, blank=True)
    action = models.CharField("Thao tác", max_length=40)
    reason = models.CharField("Lý do", max_length=255, blank=True)

    class Meta:
        ordering = ["-at", "-id"]
        verbose_name = "Nhật ký quản trị"
        verbose_name_plural = "Nhật ký quản trị"


class ProductImage(models.Model):
    """Ảnh phụ của sản phẩm (ảnh bìa vẫn là Product.image). Tổng ảnh bìa + ảnh phụ tối đa PRODUCT_IMAGE_MAX_COUNT."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="extra_images")
    image = models.ImageField("Ảnh", upload_to="products/")
    position = models.PositiveSmallIntegerField("Thứ tự", default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        verbose_name = "Ảnh phụ sản phẩm"
        verbose_name_plural = "Ảnh phụ sản phẩm"
