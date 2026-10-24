"""Nghiệp vụ đặt hàng: tính giảm giá, đặt hàng tách đơn, đổi trạng thái, hủy đơn, đánh giá, tác vụ theo hạn.

Mọi thao tác ghi nhiều bảng đều chạy trong một giao dịch cơ sở dữ liệu (NFR01); tồn kho và lượt dùng mã
được trừ bằng UPDATE có điều kiện nên an toàn khi nhiều khách đặt đồng thời.
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from catalog.models import BehaviorLog, Product, Shop, Variant

from .models import (CancelRequest, Coupon, CouponUse, Notification, Order, OrderGroup, OrderItem,
                     OrderStatusLog, PaymentTransaction, Review)

logger = logging.getLogger(__name__)

# ---- Tham số tạm chốt cho các điểm "Open Issues" ----
SHIPPING_FEE = 30000            # phí vận chuyển cố định mỗi đơn (tài liệu chưa quy định cách tính)
CANCEL_AUTO_ACCEPT_HOURS = 24   # quá hạn Người bán không phản hồi yêu cầu hủy thì tự chấp nhận
AUTO_COMPLETE_DAYS = 7          # tự hoàn thành đơn sau 7 ngày kể từ Đang giao


class OrderError(Exception):
    """Lỗi nghiệp vụ, thông điệp hiển thị trực tiếp cho người dùng."""


def vnd(n):
    return f"{int(n):,}".replace(",", ".") + " đ"


# --------------------------------------------------------------- thông báo
def notify(user, content, link=""):
    """Thông báo trên website. Lỗi tạo thông báo không làm hỏng giao dịch chính."""
    if user is None:
        return
    try:
        with transaction.atomic():
            Notification.objects.create(user=user, content=content[:500], link=link[:200])
    except Exception:  # noqa: BLE001
        logger.warning("Không tạo được thông báo", exc_info=True)


def _log(order, old, new, actor, note=""):
    OrderStatusLog.objects.create(order=order, old_status=old, new_status=new, actor=actor, note=note[:255])


# ------------------------------------------------------------- mã giảm giá
def calc_discount(coupon: Coupon, base) -> int:
    base = int(base)
    d = base * coupon.value // 100 if coupon.kind == Coupon.PERCENT else coupon.value
    if coupon.max_discount:
        d = min(d, coupon.max_discount)
    return max(0, min(d, base))


def validate_coupon(code, scope, base, shop=None, now=None) -> Coupon:
    now = now or timezone.now()
    code = (code or "").strip().upper()
    c = Coupon.objects.filter(code=code).first()
    if c is None:
        raise OrderError(f"Mã {code} không tồn tại.")
    if c.scope != scope:
        raise OrderError(f"Mã {code} là mã {'toàn sàn' if c.scope == Coupon.GLOBAL else 'của gian hàng'}, không nhập ở ô này.")
    if scope == Coupon.SHOP and c.shop_id != shop.pk:
        raise OrderError(f"Mã {code} không áp dụng cho gian hàng {shop.name}.")
    if not c.is_active:
        raise OrderError(f"Mã {code} đang tạm ngưng.")
    if now < c.starts:
        raise OrderError(f"Mã {code} chưa đến ngày bắt đầu.")
    if now > c.expires:
        raise OrderError(f"Mã {code} đã hết hạn.")
    if c.used_count >= c.max_uses:
        raise OrderError(f"Mã {code} đã hết lượt sử dụng.")
    if base < c.min_order:
        raise OrderError(f"Mã {code} chỉ áp dụng cho đơn từ {vnd(c.min_order)}.")
    return c


@dataclass
class ShopPart:
    shop: object
    lines: list
    subtotal: int
    coupon: object = None
    shop_discount: int = 0
    global_share: int = 0
    shipping: int = SHIPPING_FEE

    @property
    def discount(self):
        return self.shop_discount + self.global_share

    @property
    def total(self):
        return self.subtotal - self.discount + self.shipping


@dataclass
class Checkout:
    parts: list
    global_coupon: object = None
    errors: dict = field(default_factory=dict)

    @property
    def subtotal(self):
        return sum(p.subtotal for p in self.parts)

    @property
    def discount(self):
        return sum(p.discount for p in self.parts)

    @property
    def shipping(self):
        return sum(p.shipping for p in self.parts)

    @property
    def total(self):
        return sum(p.total for p in self.parts)

    @property
    def global_discount(self):
        return sum(p.global_share for p in self.parts)


def build_checkout(lines, global_code="", shop_codes=None, now=None) -> Checkout:
    """lines: [{'v': Variant, 'qty': int}]. Lỗi mã giảm giá không ném ra mà ghi vào errors để xem trước."""
    shop_codes = shop_codes or {}
    groups = {}
    for ln in lines:
        groups.setdefault(ln["v"].product.shop, []).append(ln)
    parts = [ShopPart(shop=s, lines=ls, subtotal=sum(int(l["v"].price) * l["qty"] for l in ls)) for s, ls in groups.items()]
    co = Checkout(parts=parts)

    for p in parts:
        code = (shop_codes.get(p.shop.pk) or "").strip()
        if code:
            try:
                p.coupon = validate_coupon(code, Coupon.SHOP, p.subtotal, shop=p.shop, now=now)
                p.shop_discount = calc_discount(p.coupon, p.subtotal)
            except OrderError as e:
                co.errors[f"shop_{p.shop.pk}"] = str(e)

    gcode = (global_code or "").strip()
    total_sub = sum(p.subtotal for p in parts)
    if gcode and parts:
        try:
            co.global_coupon = validate_coupon(gcode, Coupon.GLOBAL, total_sub, now=now)
            gd = calc_discount(co.global_coupon, total_sub)
            # phân bổ theo tỷ lệ tạm tính, làm tròn xuống đến đồng; phần dư cộng vào đơn có tạm tính lớn nhất
            shares = [gd * p.subtotal // total_sub for p in parts]
            biggest = max(range(len(parts)), key=lambda i: parts[i].subtotal)
            shares[biggest] += gd - sum(shares)
            for p, sh in zip(parts, shares):
                p.global_share = max(0, min(sh, p.subtotal - p.shop_discount))
        except OrderError as e:
            co.errors["global"] = str(e)
    return co


def _consume(coupon: Coupon, now):
    """Tăng lượt dùng bằng UPDATE có điều kiện: không vượt số lượt tối đa dù nhiều khách đặt cùng lúc."""
    n = Coupon.objects.filter(pk=coupon.pk, is_active=True, used_count__lt=F("max_uses"), starts__lte=now, expires__gte=now) \
        .update(used_count=F("used_count") + 1)
    if n != 1:
        raise OrderError(f"Mã {coupon.code} vừa hết lượt hoặc hết hạn, vui lòng bỏ mã hoặc chọn mã khác.")


def _release(use: CouponUse):
    Coupon.objects.filter(pk=use.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
    use.refunded = True
    use.save(update_fields=["refunded"])


# ---------------------------------------------------------------- đặt hàng
def place_order(user, wanted, info, payment_method, global_code="", shop_codes=None, clear_cart=True):
    """Đặt hàng từ giỏ: kiểm tra tồn kho, áp mã, tách đơn theo gian hàng, trừ tồn kho. Trả về OrderGroup.

    wanted: {variant_id: qty}; info: {'name','phone','address'}.
    clear_cart=False: dùng cho "Mua ngay" (không đụng tới giỏ hàng hiện có).
    """
    if not wanted:
        raise OrderError("Giỏ hàng đang trống.")
    if payment_method not in (OrderGroup.COD, OrderGroup.ONLINE):
        raise OrderError("Vui lòng chọn phương thức thanh toán hợp lệ.")
    for key, label in (("name", "tên người nhận"), ("phone", "số điện thoại"), ("address", "địa chỉ nhận hàng")):
        if not (info.get(key) or "").strip():
            raise OrderError(f"Vui lòng nhập {label}.")
    now = timezone.now()
    with transaction.atomic():
        locked = Variant.objects.select_for_update(of=("self",)).filter(pk__in=list(wanted)) \
            .select_related("product__shop", "product__category").order_by("pk")
        by_id = {v.pk: v for v in locked}
        lines = []
        for vid, qty in sorted(wanted.items()):
            v = by_id.get(vid)
            if v is None or v.product.status != Product.VISIBLE or v.product.shop.status != Shop.ACTIVE:
                raise OrderError("Có sản phẩm đã ngừng bán, vui lòng kiểm tra lại giỏ hàng.")
            if qty < 1 or qty > v.stock:
                raise OrderError(f"\"{v.product.name}\" ({v.name}) chỉ còn {v.stock} sản phẩm khả dụng, vui lòng điều chỉnh giỏ hàng.")
            lines.append({"v": v, "qty": qty})

        co = build_checkout(lines, global_code, shop_codes, now=now)
        if co.errors:
            raise OrderError(next(iter(co.errors.values())))

        group = OrderGroup.objects.create(
            user=user, recipient_name=info["name"].strip(), recipient_phone=info["phone"].strip(),
            address=info["address"].strip(), payment_method=payment_method, global_coupon=co.global_coupon,
            subtotal=co.subtotal, discount=co.discount, shipping_fee=co.shipping, total=co.total, created=now,
            # thanh toán trực tuyến: giữ kho 15 phút kể từ khi đặt thành công, dùng chung cho mọi giao dịch của nhóm
            hold_until=(now + timedelta(minutes=getattr(settings, "PAYMENT_HOLD_MINUTES", 15)))
            if payment_method == OrderGroup.ONLINE else None)
        if co.global_coupon:
            _consume(co.global_coupon, now)
            CouponUse.objects.create(coupon=co.global_coupon, group=group, user=user, amount=co.global_discount)

        for part in co.parts:
            order = Order.objects.create(
                group=group, shop=part.shop, shop_coupon=part.coupon, subtotal=part.subtotal,
                shop_discount=part.shop_discount, global_discount=part.global_share,
                shipping_fee=part.shipping, total=part.total, created=now)
            OrderItem.objects.bulk_create([
                OrderItem(order=order, variant=l["v"], product_name=l["v"].product.name, variant_name=l["v"].name,
                          unit_price=l["v"].price, qty=l["qty"]) for l in part.lines])
            for l in part.lines:   # trừ tồn kho ngay khi đặt thành công
                n = Variant.objects.filter(pk=l["v"].pk, stock__gte=l["qty"]).update(stock=F("stock") - l["qty"])
                if n != 1:
                    raise OrderError("Tồn kho vừa thay đổi, vui lòng thử đặt lại.")
            if part.coupon:
                _consume(part.coupon, now)
                CouponUse.objects.create(coupon=part.coupon, group=group, order=order, user=user, amount=part.shop_discount)
            _log(order, "", Order.PENDING, user, "Khách hàng đặt hàng")
            notify(part.shop.owner, f"Có đơn hàng mới #{order.pk} ({vnd(order.total)})", f"/quan-ly/don-hang/{order.pk}/")

        if clear_cart:
            _clear_cart(user, list(wanted))
    return group


def _clear_cart(user, variant_ids):
    from .models import CartItem
    CartItem.objects.filter(user=user, variant_id__in=variant_ids).delete()


# ------------------------------------------------------------ truy xuất đơn
def _lock_order(order_id):
    try:
        return Order.objects.select_for_update(of=("self",)).select_related("shop__owner", "group__user").get(pk=order_id)
    except Order.DoesNotExist:
        raise OrderError("Không tìm thấy đơn hàng.")


def _check_customer(order, user):
    if order.group.user_id != user.pk:
        raise OrderError("Đơn hàng không thuộc tài khoản của bạn.")


def _check_vendor(order, user):
    if order.shop.owner_id != user.pk:
        raise OrderError("Đơn hàng không thuộc gian hàng của bạn.")


# ----------------------------------------------------------------- hủy đơn
def cancel_order(order_id, actor, reason, auto=False):
    """Hủy đơn: hoàn tồn kho, hoàn lượt mã, chuyển trạng thái thanh toán, ghi nhật ký (cùng một giao dịch)."""
    with transaction.atomic():
        order = _lock_order(order_id)
        if order.status == Order.CANCELED:
            raise OrderError("Đơn hàng đã được hủy trước đó.")
        if order.status not in (Order.PENDING, Order.CONFIRMED):
            raise OrderError("Đơn đang giao hoặc đã hoàn thành không được hủy.")

        restored = []
        for item in sorted(order.items.all(), key=lambda i: i.variant_id):
            v = Variant.objects.select_for_update().get(pk=item.variant_id)
            Variant.objects.filter(pk=v.pk).update(stock=F("stock") + item.qty)
            restored.append({"item": item, "before": v.stock, "after": v.stock + item.qty})

        old = order.status
        order.status = Order.CANCELED
        order.cancel_reason = (reason or "")[:255]
        if order.payment_status == Order.PAID:
            order.payment_status = Order.REFUND_WAIT    # hoàn tiền mô phỏng trong Sandbox
        elif order.payment_status == Order.UNPAID:
            # đơn chưa thanh toán bị hủy: giao dịch đang chờ của nhóm hết hiệu lực, khách tạo giao dịch mới cho phần còn lại (4b)
            PaymentTransaction.objects.filter(group_id=order.group_id, status=PaymentTransaction.PENDING) \
                .update(status=PaymentTransaction.SUPERSEDED)
        order.save(update_fields=["status", "cancel_reason", "payment_status"])

        for use in CouponUse.objects.select_for_update().filter(order=order, refunded=False):
            _release(use)
        guse = CouponUse.objects.filter(group=order.group, order__isnull=True, refunded=False).first()
        if guse and not Order.objects.filter(group=order.group).exclude(status=Order.CANCELED).exists():
            _release(guse)

        now = timezone.now()
        order.cancel_requests.filter(result=CancelRequest.PENDING).update(
            result=CancelRequest.ACCEPTED, resolved_at=now, auto_accepted=auto)
        _log(order, old, Order.CANCELED, actor, ("Tự động hủy: " if auto else "") + (reason or ""))
        notify(order.group.user, f"Đơn hàng #{order.pk} đã bị hủy. Lý do: {reason}", f"/don-hang/{order.pk}/")
        if actor is None or actor.pk != order.shop.owner_id:
            notify(order.shop.owner, f"Đơn hàng #{order.pk} đã bị hủy. Lý do: {reason}", f"/quan-ly/don-hang/{order.pk}/")
    return restored


def customer_cancel(user, order_id, reason):
    """Trả về 'DA_HUY' (hủy ngay) hoặc 'DA_GUI' (đã gửi yêu cầu cho Người bán)."""
    reason = (reason or "").strip()
    if not reason:
        raise OrderError("Vui lòng nhập lý do hủy.")
    with transaction.atomic():
        order = _lock_order(order_id)
        _check_customer(order, user)
        if order.status == Order.PENDING:
            CancelRequest.objects.create(order=order, requested_by=CancelRequest.BY_CUSTOMER, user=user, reason=reason[:255],
                                         result=CancelRequest.ACCEPTED, resolved_at=timezone.now())
            cancel_order(order.pk, user, reason)
            return "DA_HUY"
        if order.status == Order.CONFIRMED:
            if order.cancel_requests.filter(result=CancelRequest.PENDING).exists():
                raise OrderError("Đơn này đã có yêu cầu hủy đang chờ Người bán xử lý.")
            CancelRequest.objects.create(order=order, requested_by=CancelRequest.BY_CUSTOMER, user=user, reason=reason[:255])
            notify(order.shop.owner, f"Khách hàng yêu cầu hủy đơn #{order.pk}, cần phản hồi trong {CANCEL_AUTO_ACCEPT_HOURS} giờ",
                   f"/quan-ly/don-hang/{order.pk}/")
            return "DA_GUI"
        if order.status == Order.CANCELED:
            raise OrderError("Đơn hàng đã được hủy trước đó.")
        raise OrderError("Đơn đang giao hoặc đã hoàn thành không được hủy.")


def vendor_cancel(user, order_id, reason):
    reason = (reason or "").strip()
    if not reason:
        raise OrderError("Người bán hủy đơn phải ghi lý do.")
    with transaction.atomic():
        order = _lock_order(order_id)
        _check_vendor(order, user)
        if not order.cancel_requests.filter(result=CancelRequest.PENDING).exists():
            CancelRequest.objects.create(order=order, requested_by=CancelRequest.BY_VENDOR, user=user, reason=reason[:255],
                                         result=CancelRequest.ACCEPTED, resolved_at=timezone.now())
        return cancel_order(order.pk, user, reason)


def vendor_resolve_cancel(user, order_id, accept, reject_reason=""):
    with transaction.atomic():
        order = _lock_order(order_id)
        _check_vendor(order, user)
        req = order.cancel_requests.filter(result=CancelRequest.PENDING).first()
        if req is None:
            raise OrderError("Đơn này không có yêu cầu hủy nào đang chờ xử lý.")
        if accept:
            cancel_order(order.pk, user, req.reason)
            return "CHAP_NHAN"
        reject_reason = (reject_reason or "").strip()
        if not reject_reason:
            raise OrderError("Từ chối yêu cầu hủy phải ghi lý do.")
        req.result, req.reject_reason, req.resolved_at = CancelRequest.REJECTED, reject_reason[:255], timezone.now()
        req.save(update_fields=["result", "reject_reason", "resolved_at"])
        notify(order.group.user, f"Yêu cầu hủy đơn #{order.pk} bị từ chối. Lý do: {reject_reason}", f"/don-hang/{order.pk}/")
        return "TU_CHOI"


# ------------------------------------------------------- cập nhật trạng thái
def update_status(user, order_id, new_status, carrier="", tracking=""):
    """Người bán chuyển tuần tự: Chờ xác nhận -> Đã xác nhận -> Đang giao (QĐ10)."""
    carrier, tracking = (carrier or "").strip(), (tracking or "").strip()
    try:
        with transaction.atomic():
            order = _lock_order(order_id)
            _check_vendor(order, user)
            old = order.status
            if old in (Order.DONE, Order.CANCELED):
                raise OrderError("Đơn đã ở trạng thái cuối, không được chuyển tiếp hoặc quay lại.")
            if new_status == Order.DONE:
                raise OrderError("Người bán không tự chuyển đơn sang Hoàn thành: do khách hàng xác nhận đã nhận hoặc tự động sau 7 ngày.")
            if new_status == Order.CONFIRMED and old == Order.PENDING:
                if order.group.payment_method == OrderGroup.ONLINE and order.payment_status != Order.PAID:
                    raise OrderError("Đơn thanh toán trực tuyến chỉ được xác nhận khi đã thanh toán.")
            elif new_status == Order.SHIPPING and old == Order.CONFIRMED:
                if order.cancel_requests.filter(result=CancelRequest.PENDING).exists():
                    raise OrderError("Đơn còn yêu cầu hủy chờ xử lý, hãy chấp nhận hoặc từ chối trước khi giao.")
                if not carrier or not tracking:
                    raise OrderError("Nhập đơn vị vận chuyển và mã vận đơn khi chuyển sang Đang giao.")
                if Order.objects.filter(carrier__iexact=carrier, tracking_code=tracking).exclude(pk=order.pk).exists():
                    raise OrderError("Mã vận đơn này đã tồn tại với đơn vị vận chuyển đã chọn.")
                order.carrier, order.tracking_code, order.shipped_at = carrier, tracking, timezone.now()
            else:
                raise OrderError("Trạng thái chỉ được chuyển tuần tự, không bỏ qua bước trung gian hoặc quay lại.")
            order.status = new_status
            order.save()
            _log(order, old, new_status, user, f"{carrier} {tracking}".strip())
            label = dict(Order.STATUS)[new_status].lower()
            notify(order.group.user, f"Đơn hàng #{order.pk} {label}", f"/don-hang/{order.pk}/")
    except IntegrityError:
        raise OrderError("Mã vận đơn này đã tồn tại với đơn vị vận chuyển đã chọn.")
    return order


def complete_order(order_id, actor=None, auto=False):
    with transaction.atomic():
        order = _lock_order(order_id)
        if order.status != Order.SHIPPING:
            raise OrderError("Chỉ đơn đang giao mới xác nhận đã nhận hàng được.")
        order.status = Order.DONE
        if order.payment_status == Order.UNPAID and order.group.payment_method == OrderGroup.COD:
            order.payment_status = Order.PAID      # COD: đã thu tiền khi giao
        order.save(update_fields=["status", "payment_status"])
        _log(order, Order.SHIPPING, Order.DONE, actor, "Tự động hoàn thành sau 7 ngày" if auto else "Khách hàng xác nhận đã nhận hàng")
        try:   # PURCHASE ghi khi đơn Hoàn thành, mỗi sản phẩm một dòng; lỗi log không làm hỏng giao dịch (NV9)
            with transaction.atomic():
                pids = {i.variant.product_id for i in order.items.select_related("variant")}
                BehaviorLog.objects.bulk_create([
                    BehaviorLog(user=order.group.user, product_id=p, type=BehaviorLog.PURCHASE, source="DON_HANG") for p in pids])
        except Exception:  # noqa: BLE001
            logger.warning("Không ghi được log PURCHASE", exc_info=True)
        notify(order.shop.owner, f"Đơn hàng #{order.pk} đã hoàn thành", f"/quan-ly/don-hang/{order.pk}/")
        if auto:
            notify(order.group.user, f"Đơn hàng #{order.pk} tự động hoàn thành. Bạn có thể đánh giá sản phẩm.", f"/don-hang/{order.pk}/")
    return order


def confirm_received(user, order_id):
    order = Order.objects.select_related("group").filter(pk=order_id).first()
    if order is None:
        raise OrderError("Không tìm thấy đơn hàng.")
    _check_customer(order, user)
    return complete_order(order_id, actor=user)


def run_timeouts(now=None):
    """Tác vụ theo hạn, chạy lại không gây xử lý trùng (NFR10)."""
    now = now or timezone.now()
    accepted = completed = 0
    from . import payments   # tránh import vòng
    try:
        payments.expire_overdue(now)
    except Exception:  # noqa: BLE001
        logger.warning("Không xử lý được giao dịch quá hạn giữ kho", exc_info=True)
    pending = CancelRequest.objects.filter(
        result=CancelRequest.PENDING, requested_by=CancelRequest.BY_CUSTOMER,
        created__lte=now - timedelta(hours=CANCEL_AUTO_ACCEPT_HOURS), order__status=Order.CONFIRMED)
    for req in pending:
        try:
            cancel_order(req.order_id, None, req.reason, auto=True)
            accepted += 1
        except OrderError:
            pass
    for oid in Order.objects.filter(status=Order.SHIPPING, shipped_at__lte=now - timedelta(days=AUTO_COMPLETE_DAYS)) \
            .values_list("pk", flat=True):
        try:
            complete_order(oid, actor=None, auto=True)
            completed += 1
        except OrderError:
            pass
    return accepted, completed


# ----------------------------------------------------------------- đánh giá
def can_review(user, product_id):
    """Đơn Hoàn thành chứa sản phẩm và chưa đánh giá. Trả về đơn đủ điều kiện hoặc None."""
    if Review.objects.filter(user=user, product_id=product_id).exists():
        return None
    return Order.objects.filter(group__user=user, status=Order.DONE, items__variant__product_id=product_id).order_by("-created").first()


def create_review(user, order_id, product_id, rating, comment=""):
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        raise OrderError("Số sao phải là số nguyên từ 1 đến 5.")
    if not 1 <= rating <= 5:
        raise OrderError("Số sao phải là số nguyên từ 1 đến 5.")
    order = Order.objects.select_related("group").filter(pk=order_id).first()
    if order is None or order.group.user_id != user.pk:
        raise OrderError("Đơn hàng không thuộc tài khoản của bạn.")
    if order.status != Order.DONE:
        raise OrderError("Chỉ đánh giá được sản phẩm của đơn đã Hoàn thành.")
    if not OrderItem.objects.filter(order=order, variant__product_id=product_id).exists():
        raise OrderError("Sản phẩm này không có trong đơn hàng.")
    if Review.objects.filter(user=user, product_id=product_id).exists():
        raise OrderError("Bạn đã đánh giá sản phẩm này rồi.")
    try:
        with transaction.atomic():
            return Review.objects.create(user=user, product_id=product_id, order=order, rating=rating, comment=(comment or "").strip()[:1000])
    except IntegrityError:
        raise OrderError("Bạn đã đánh giá sản phẩm này rồi.")


# -------------------------------------------------- hoàn tiền mô phỏng (Sandbox)
def complete_refund(order_id, actor=None):
    """Hoàn tất hoàn tiền mô phỏng cho đơn đã thanh toán trực tuyến rồi bị hủy: Chờ hoàn tiền -> Đã hoàn tiền."""
    with transaction.atomic():
        order = _lock_order(order_id)
        if order.payment_status != Order.REFUND_WAIT:
            raise OrderError("Đơn này không ở trạng thái Chờ hoàn tiền.")
        order.payment_status = Order.REFUNDED
        order.save(update_fields=["payment_status"])
        _log(order, order.status, order.status, actor, f"Đã hoàn tiền (mô phỏng) {vnd(order.total)}")
        notify(order.group.user, f"Đơn hàng #{order.pk} đã được hoàn tiền {vnd(order.total)} (mô phỏng Sandbox)", f"/don-hang/{order.pk}/")
    return order


def complete_late_refund(txn_id, actor=None):
    """Hoàn tiền mô phỏng cho giao dịch Thanh toán muộn."""
    with transaction.atomic():
        txn = PaymentTransaction.objects.select_for_update(of=("self",)).select_related("group__user").filter(pk=txn_id).first()
        if txn is None or txn.refund_status != PaymentTransaction.REFUND_WAIT:
            raise OrderError("Giao dịch này không ở trạng thái Chờ hoàn tiền.")
        txn.refund_status = PaymentTransaction.REFUNDED
        txn.save(update_fields=["refund_status"])
        notify(txn.group.user, f"Giao dịch {txn.ref} đã được hoàn tiền {vnd(txn.amount)} (mô phỏng Sandbox)", "/don-hang/")
    return txn


# ---------------------------------------------------- xóa sản phẩm (UC13)
def delete_product(user, product_id):
    """Người bán xóa sản phẩm của gian hàng mình. Đã phát sinh đơn hàng thì chỉ ẨN (xóa mềm); chưa có đơn thì xóa hẳn.
    Trả về 'DA_AN' hoặc 'DA_XOA'."""
    p = Product.objects.select_related("shop").filter(pk=product_id).first()
    if p is None or p.shop.owner_id != user.pk:
        raise OrderError("Sản phẩm không thuộc gian hàng của bạn.")
    with transaction.atomic():
        if OrderItem.objects.filter(variant__product_id=p.pk).exists():
            if p.status == Product.VISIBLE:
                p.status = Product.HIDDEN
                p.save()
            return "DA_AN"
        p.delete()
        return "DA_XOA"
