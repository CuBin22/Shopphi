from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class CartItem(models.Model):
    """Giỏ hàng của khách hàng đã đăng nhập (lưu trong PostgreSQL). Mỗi cặp (khách hàng, biến thể) một dòng."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.CASCADE, related_name="+")
    qty = models.PositiveIntegerField("Số lượng", default=1)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Dòng giỏ hàng"
        verbose_name_plural = "Giỏ hàng"
        constraints = [models.UniqueConstraint(fields=["user", "variant"], name="uq_cart_user_variant"),
                       models.CheckConstraint(condition=Q(qty__gte=1), name="ck_cart_qty_min1")]


class Coupon(models.Model):
    GLOBAL, SHOP = "TOAN_SAN", "GIAN_HANG"
    SCOPES = [(GLOBAL, "Toàn sàn"), (SHOP, "Gian hàng")]
    PERCENT, AMOUNT = "PHAN_TRAM", "SO_TIEN"
    KINDS = [(PERCENT, "Giảm theo %"), (AMOUNT, "Giảm số tiền")]

    code = models.CharField("Mã code", max_length=30, unique=True)
    scope = models.CharField("Phạm vi", max_length=10, choices=SCOPES)
    shop = models.ForeignKey("catalog.Shop", null=True, blank=True, on_delete=models.CASCADE, related_name="coupons",
                             verbose_name="Gian hàng")
    kind = models.CharField("Loại giảm", max_length=10, choices=KINDS, default=PERCENT)
    value = models.PositiveIntegerField("Giá trị giảm (% hoặc đ)")
    max_discount = models.PositiveIntegerField("Mức giảm tối đa (đ)", null=True, blank=True)
    min_order = models.PositiveIntegerField("Đơn tối thiểu (đ)", default=0)
    starts = models.DateTimeField("Ngày bắt đầu")
    expires = models.DateTimeField("Ngày hết hạn")
    max_uses = models.PositiveIntegerField("Số lượt tối đa", default=100)
    used_count = models.PositiveIntegerField("Số lượt đã dùng", default=0, editable=False)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False)
    created = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Mã giảm giá"
        verbose_name_plural = "Mã giảm giá"
        constraints = [
            models.CheckConstraint(condition=Q(expires__gt=F("starts")), name="ck_coupon_dates"),
            models.CheckConstraint(condition=Q(used_count__lte=F("max_uses")), name="ck_coupon_uses"),
            models.CheckConstraint(
                condition=(Q(scope="TOAN_SAN", shop__isnull=True) | Q(scope="GIAN_HANG", shop__isnull=False)),
                name="ck_coupon_scope_shop"),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        if self.scope == self.GLOBAL and self.shop_id:
            raise ValidationError({"shop": "Mã toàn sàn không gắn với gian hàng."})
        if self.scope == self.SHOP and not self.shop_id:
            raise ValidationError({"shop": "Mã gian hàng phải chọn gian hàng."})
        if self.kind == self.PERCENT and not (1 <= (self.value or 0) <= 100):
            raise ValidationError({"value": "Giảm theo % phải từ 1 đến 100."})
        if self.value is not None and self.value < 1:
            raise ValidationError({"value": "Giá trị giảm phải lớn hơn 0."})
        if self.starts and self.expires and self.expires <= self.starts:
            raise ValidationError({"expires": "Ngày hết hạn phải sau ngày bắt đầu."})

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
        super().save(*args, **kwargs)

    @property
    def label(self):
        base = f"{self.value}%" if self.kind == self.PERCENT else f"{self.value:,}".replace(",", ".") + " đ"
        return f"Giảm {base}"


class OrderGroup(models.Model):
    """Nhóm đơn: các đơn tách theo gian hàng từ một lần đặt hàng (BM9)."""
    COD, ONLINE = "COD", "CONG_THANH_TOAN"
    METHODS = [(COD, "Thanh toán khi nhận hàng (COD)"), (ONLINE, "Cổng thanh toán (Sandbox)")]

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="order_groups")
    recipient_name = models.CharField("Người nhận", max_length=80)
    recipient_phone = models.CharField("Số điện thoại", max_length=20)
    address = models.CharField("Địa chỉ nhận hàng", max_length=255)
    payment_method = models.CharField("Phương thức thanh toán", max_length=16, choices=METHODS, default=COD)
    global_coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField("Tổng thanh toán của nhóm", max_digits=12, decimal_places=0, default=0)
    created = models.DateTimeField("Thời điểm đặt", default=timezone.now)
    hold_until = models.DateTimeField("Hạn giữ kho (thanh toán trực tuyến)", null=True, blank=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Nhóm đơn"
        verbose_name_plural = "Nhóm đơn"

    def __str__(self):
        return f"Nhóm đơn #{self.pk}"


class Order(models.Model):
    PENDING, CONFIRMED, SHIPPING, DONE, CANCELED = "CHO_XAC_NHAN", "DA_XAC_NHAN", "DANG_GIAO", "HOAN_THANH", "DA_HUY"
    STATUS = [(PENDING, "Chờ xác nhận"), (CONFIRMED, "Đã xác nhận"), (SHIPPING, "Đang giao"),
              (DONE, "Hoàn thành"), (CANCELED, "Đã hủy")]
    UNPAID, PAID, REFUND_WAIT, REFUNDED = "CHUA_THANH_TOAN", "DA_THANH_TOAN", "CHO_HOAN_TIEN", "DA_HOAN_TIEN"
    PAY_STATUS = [(UNPAID, "Chưa thanh toán"), (PAID, "Đã thanh toán"), (REFUND_WAIT, "Chờ hoàn tiền"), (REFUNDED, "Đã hoàn tiền")]

    group = models.ForeignKey(OrderGroup, on_delete=models.PROTECT, related_name="orders")
    shop = models.ForeignKey("catalog.Shop", on_delete=models.PROTECT, related_name="orders")
    status = models.CharField("Trạng thái xử lý", max_length=14, choices=STATUS, default=PENDING, db_index=True)
    payment_status = models.CharField("Trạng thái thanh toán", max_length=16, choices=PAY_STATUS, default=UNPAID)
    shop_coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    subtotal = models.DecimalField("Tạm tính", max_digits=12, decimal_places=0)
    shop_discount = models.DecimalField("Giảm giá gian hàng", max_digits=12, decimal_places=0, default=0)
    global_discount = models.DecimalField("Giảm giá toàn sàn (phân bổ)", max_digits=12, decimal_places=0, default=0)
    shipping_fee = models.DecimalField("Phí vận chuyển", max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField("Tổng thanh toán", max_digits=12, decimal_places=0)
    carrier = models.CharField("Đơn vị vận chuyển", max_length=60, blank=True)
    tracking_code = models.CharField("Mã vận đơn", max_length=60, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField("Lý do hủy", max_length=255, blank=True)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Đơn hàng"
        verbose_name_plural = "Đơn hàng"
        constraints = [
            models.UniqueConstraint(Lower("carrier"), "tracking_code", name="uq_order_carrier_tracking",
                                    condition=~Q(tracking_code="")),
            models.CheckConstraint(condition=Q(total__gte=0), name="ck_order_total_nonneg"),
        ]

    def __str__(self):
        return f"Đơn #{self.pk}"

    @property
    def discount(self):
        return self.shop_discount + self.global_discount

    @property
    def pending_cancel(self):
        return self.cancel_requests.filter(result=CancelRequest.PENDING).first()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT, related_name="+")
    product_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=80)
    unit_price = models.DecimalField("Đơn giá lúc đặt", max_digits=12, decimal_places=0)
    qty = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Dòng đơn hàng"
        verbose_name_plural = "Dòng đơn hàng"

    @property
    def line_total(self):
        return self.unit_price * self.qty


class OrderStatusLog(models.Model):
    """Nhật ký đổi trạng thái; actor rỗng nghĩa là hệ thống tự động (hủy/hoàn thành tự động)."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_logs")
    at = models.DateTimeField(default=timezone.now)
    old_status = models.CharField(max_length=14, blank=True)
    new_status = models.CharField(max_length=14)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["at", "id"]
        verbose_name = "Nhật ký trạng thái đơn"
        verbose_name_plural = "Nhật ký trạng thái đơn"


class CancelRequest(models.Model):
    PENDING, ACCEPTED, REJECTED = "CHO_XU_LY", "CHAP_NHAN", "TU_CHOI"
    RESULTS = [(PENDING, "Chờ xử lý"), (ACCEPTED, "Chấp nhận"), (REJECTED, "Từ chối")]
    BY_CUSTOMER, BY_VENDOR = "KHACH_HANG", "NGUOI_BAN"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="cancel_requests")
    requested_by = models.CharField(max_length=10, choices=[(BY_CUSTOMER, "Khách hàng"), (BY_VENDOR, "Người bán")])
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reason = models.CharField("Lý do hủy", max_length=255)
    result = models.CharField(max_length=10, choices=RESULTS, default=PENDING)
    reject_reason = models.CharField("Lý do từ chối", max_length=255, blank=True)
    auto_accepted = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Yêu cầu hủy đơn"
        verbose_name_plural = "Yêu cầu hủy đơn"
        constraints = [models.UniqueConstraint(fields=["order"], condition=Q(result="CHO_XU_LY"),
                                               name="uq_one_pending_cancel_per_order")]


class CouponUse(models.Model):
    """Lịch sử áp dụng mã (BM7). Mã toàn sàn: một dòng cho cả nhóm đơn; mã gian hàng: một dòng cho mỗi đơn."""
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="uses")
    group = models.ForeignKey(OrderGroup, on_delete=models.CASCADE, related_name="coupon_uses")
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="coupon_uses")
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    amount = models.DecimalField("Số tiền giảm", max_digits=12, decimal_places=0)
    refunded = models.BooleanField("Đã hoàn lượt", default=False)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Lượt dùng mã giảm giá"
        verbose_name_plural = "Lịch sử dùng mã giảm giá"


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    product = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="reviews")
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, related_name="reviews")
    rating = models.PositiveSmallIntegerField("Số sao")
    comment = models.TextField("Bình luận", blank=True, max_length=1000)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Đánh giá"
        verbose_name_plural = "Đánh giá sản phẩm"
        constraints = [
            models.UniqueConstraint(fields=["user", "product"], name="uq_review_user_product"),
            models.CheckConstraint(condition=Q(rating__gte=1, rating__lte=5), name="ck_review_rating_1_5"),
        ]


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    content = models.CharField(max_length=500)
    link = models.CharField(max_length=200, blank=True)
    read = models.BooleanField(default=False)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Thông báo"
        verbose_name_plural = "Thông báo"


class PaymentTransaction(models.Model):
    """Giao dịch thanh toán trực tuyến (Sandbox) cho một nhóm đơn (BM12). Mỗi nhóm chỉ có một giao dịch đang hiệu lực."""
    PENDING, SUCCESS, FAILED = "CHO_THANH_TOAN", "THANH_CONG", "THAT_BAI"
    EXPIRED, SUPERSEDED, LATE = "HET_HAN", "HET_HIEU_LUC", "THANH_TOAN_MUON"
    STATUS = [(PENDING, "Chờ thanh toán"), (SUCCESS, "Thành công"), (FAILED, "Thất bại / hủy tại cổng"),
              (EXPIRED, "Hết hạn giữ kho"), (SUPERSEDED, "Hết hiệu lực"), (LATE, "Thanh toán muộn")]
    REFUND_WAIT, REFUNDED = "CHO_HOAN_TIEN", "DA_HOAN_TIEN"
    REFUND = [("", "Không"), (REFUND_WAIT, "Chờ hoàn tiền"), (REFUNDED, "Đã hoàn tiền")]

    ref = models.CharField("Mã giao dịch nội bộ", max_length=40, unique=True)
    group = models.ForeignKey(OrderGroup, on_delete=models.PROTECT, related_name="transactions")
    amount = models.DecimalField("Số tiền", max_digits=12, decimal_places=0)
    status = models.CharField("Trạng thái", max_length=16, choices=STATUS, default=PENDING, db_index=True)
    refund_status = models.CharField("Hoàn tiền (mô phỏng)", max_length=14, choices=REFUND, blank=True, default="")
    gateway_status = models.CharField("Kết quả cổng trả về", max_length=12, blank=True)
    created = models.DateTimeField(default=timezone.now)
    processed_at = models.DateTimeField("Thời điểm xử lý kết quả", null=True, blank=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Giao dịch thanh toán"
        verbose_name_plural = "Giao dịch thanh toán"
        constraints = [models.UniqueConstraint(fields=["group"], condition=Q(status="CHO_THANH_TOAN"),
                                               name="uq_one_active_txn_per_group")]

    def __str__(self):
        return f"{self.ref} ({self.get_status_display()})"
