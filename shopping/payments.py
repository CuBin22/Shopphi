"""Thanh toán trực tuyến ở môi trường Sandbox (UC07, FR11, FR22, FR23, NFR02, NFR15).

Cổng thanh toán là bản giả lập nằm trong chính dự án (trang /thanh-toan/sandbox/<mã giao dịch>/); kết quả cổng trả về
được KÝ bằng HMAC-SHA256 với khóa PAYMENT_SANDBOX_SECRET và hệ thống luôn xác thực chữ ký + đối chiếu số tiền,
mã giao dịch, mã nhóm đơn trước khi cập nhật đơn. Hệ thống không nhận, không lưu thông tin thẻ.

Quy tắc chính:
  * mỗi nhóm đơn chỉ có MỘT giao dịch đang hiệu lực (ràng buộc duy nhất trong cơ sở dữ liệu);
  * giữ kho 15 phút kể từ lúc đặt hàng thành công (OrderGroup.hold_until); thanh toán lại không kéo dài hạn;
  * mỗi giao dịch chỉ cập nhật đơn một lần (processed_at); kết quả trùng bị bỏ qua;
  * kết quả thành công đến muộn (đơn đã hủy / hết hạn / thanh toán bằng giao dịch khác) -> "Thanh toán muộn" + Chờ hoàn tiền.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Order, OrderGroup, PaymentTransaction
from .services import OrderError, _log, cancel_order, notify, vnd

SIGN_FIELDS = ("txn_ref", "group", "amount", "status")
GATEWAY_RESULTS = {"success": "SUCCESS", "fail": "FAILED", "cancel": "CANCELED"}


class PaymentError(OrderError):
    """Lỗi thanh toán, thông điệp hiển thị trực tiếp cho người dùng."""


# ------------------------------------------------------------------ chữ ký
def sign(params) -> str:
    msg = "&".join(f"{k}={params[k]}" for k in SIGN_FIELDS)
    key = settings.PAYMENT_SANDBOX_SECRET.encode("utf-8")
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).hexdigest()


def build_callback(txn: PaymentTransaction, result: str) -> dict:
    """Phía cổng Sandbox: tạo tham số kết quả đã ký gửi về hệ thống."""
    status = GATEWAY_RESULTS.get(result, "CANCELED")
    params = {"txn_ref": txn.ref, "group": str(txn.group_id), "amount": str(int(txn.amount)), "status": status}
    params["sig"] = sign(params)
    return params


# -------------------------------------------------------------- hết hạn giữ kho
def _expire_group(group_id, now):
    with transaction.atomic():
        group = OrderGroup.objects.select_for_update().get(pk=group_id)
        PaymentTransaction.objects.filter(group=group, status=PaymentTransaction.PENDING) \
            .update(status=PaymentTransaction.EXPIRED)
        ids = list(Order.objects.filter(group=group, status=Order.PENDING, payment_status=Order.UNPAID)
                   .values_list("pk", flat=True))
        done = 0
        for oid in ids:
            try:
                cancel_order(oid, None, f"Quá hạn giữ kho {getattr(settings, 'PAYMENT_HOLD_MINUTES', 15)} phút chưa thanh toán", auto=True)
                done += 1
            except OrderError:
                pass
    return done


def expire_overdue(now=None, group_id=None) -> int:
    """Hủy giao dịch + đơn chưa thanh toán đã quá hạn giữ kho và hoàn trả tồn kho. Chạy lại không gây xử lý trùng."""
    now = now or timezone.now()
    qs = OrderGroup.objects.filter(payment_method=OrderGroup.ONLINE, hold_until__lte=now,
                                   orders__status=Order.PENDING, orders__payment_status=Order.UNPAID).distinct()
    if group_id is not None:
        qs = qs.filter(pk=group_id)
    total = 0
    for gid in list(qs.values_list("pk", flat=True)):
        total += _expire_group(gid, now)
    return total


# ------------------------------------------------------------ tạo yêu cầu (FR11)
def payable_orders(group):
    return [o for o in Order.objects.filter(group=group).exclude(status=Order.CANCELED) if o.payment_status == Order.UNPAID]


def create_payment(user, group_id, now=None) -> PaymentTransaction:
    now = now or timezone.now()
    base = OrderGroup.objects.filter(pk=group_id).first()
    if base is None or base.user_id != user.pk:
        raise PaymentError("Không tìm thấy nhóm đơn của bạn.")
    expire_overdue(now, group_id=base.pk)
    with transaction.atomic():
        group = OrderGroup.objects.select_for_update().get(pk=group_id)
        if group.payment_method != OrderGroup.ONLINE:
            raise PaymentError("Nhóm đơn này chọn thanh toán khi nhận hàng (COD), không cần thanh toán trực tuyến.")
        unpaid = [o for o in Order.objects.select_for_update().filter(group=group).exclude(status=Order.CANCELED)
                  if o.payment_status == Order.UNPAID]
        if not unpaid:
            if group.hold_until and now > group.hold_until and Order.objects.filter(group=group, status=Order.CANCELED).exists():
                raise PaymentError("Đã quá hạn giữ kho, đơn chưa thanh toán đã bị hủy và tồn kho đã được hoàn trả.")
            raise PaymentError("Nhóm đơn không còn đơn nào cần thanh toán (đã thanh toán hoặc đã hủy).")
        # thanh toán lại: giao dịch cũ hết hiệu lực, giao dịch mới có cùng hạn giữ kho của nhóm đơn
        PaymentTransaction.objects.filter(group=group, status=PaymentTransaction.PENDING) \
            .update(status=PaymentTransaction.SUPERSEDED)
        txn = PaymentTransaction.objects.create(
            ref="TXN" + secrets.token_hex(8).upper(), group=group, amount=sum(o.total for o in unpaid), created=now)
    return txn


# ------------------------------------------------------- xử lý kết quả (FR22)
def process_result(params, now=None):
    """Trả về (kết_quả, giao_dịch); kết_quả in THANH_CONG | THAT_BAI | BO_QUA | THANH_TOAN_MUON.
    Ném PaymentError khi chữ ký sai hoặc không khớp số tiền / mã giao dịch / mã nhóm đơn (đơn không bị cập nhật)."""
    now = now or timezone.now()
    p = {k: str(params.get(k, "")) for k in SIGN_FIELDS}
    if not hmac.compare_digest(sign(p), str(params.get("sig", ""))):
        raise PaymentError("Chữ ký kết quả thanh toán không hợp lệ, kết quả bị từ chối.")
    first = PaymentTransaction.objects.filter(ref=p["txn_ref"]).first()
    if first is None:
        raise PaymentError("Không tìm thấy giao dịch thanh toán, kết quả bị từ chối.")
    expire_overdue(now, group_id=first.group_id)       # xử lý hạn giữ kho trước khi áp kết quả

    with transaction.atomic():
        txn = PaymentTransaction.objects.select_for_update(of=("self",)).select_related("group__user").get(pk=first.pk)
        if str(txn.group_id) != p["group"] or str(int(txn.amount)) != p["amount"]:
            raise PaymentError("Số tiền hoặc mã nhóm đơn không khớp giao dịch, kết quả bị từ chối.")
        if txn.processed_at is not None:
            return "BO_QUA", txn                     # mỗi giao dịch chỉ cập nhật đơn một lần

        txn.gateway_status = p["status"][:12]
        txn.processed_at = now
        user = txn.group.user

        if p["status"] != "SUCCESS":
            if txn.status == PaymentTransaction.PENDING:
                txn.status = PaymentTransaction.FAILED
            txn.save(update_fields=["gateway_status", "processed_at", "status"])
            return "THAT_BAI", txn

        orders = list(Order.objects.select_for_update(of=("self",)).select_related("shop__owner").filter(group_id=txn.group_id))
        unpaid = [o for o in orders if o.status != Order.CANCELED and o.payment_status == Order.UNPAID]
        valid = txn.status == PaymentTransaction.PENDING and unpaid and sum(o.total for o in unpaid) == txn.amount
        if not valid:
            txn.status = PaymentTransaction.LATE
            txn.refund_status = PaymentTransaction.REFUND_WAIT
            txn.save(update_fields=["gateway_status", "processed_at", "status", "refund_status"])
            notify(user, f"Giao dịch {txn.ref} đến muộn, số tiền {vnd(txn.amount)} đang chờ hoàn tiền (mô phỏng Sandbox)", "/don-hang/")
            return "THANH_TOAN_MUON", txn

        for o in unpaid:
            o.payment_status = Order.PAID
            o.save(update_fields=["payment_status"])
            _log(o, o.status, o.status, None, f"Thanh toán thành công qua cổng Sandbox ({txn.ref})")
            notify(user, f"Đơn hàng #{o.pk} đã thanh toán thành công", f"/don-hang/{o.pk}/")
            notify(o.shop.owner, f"Đơn hàng #{o.pk} đã được thanh toán, bạn có thể xác nhận đơn", f"/quan-ly/don-hang/{o.pk}/")
        txn.status = PaymentTransaction.SUCCESS
        txn.save(update_fields=["gateway_status", "processed_at", "status"])
        return "THANH_CONG", txn
