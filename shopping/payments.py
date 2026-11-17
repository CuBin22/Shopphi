"""Thanh toán trực tuyến (UC07, FR11, FR22, FR23, NFR02, NFR15).

Hai cổng, chọn bằng settings.PAYMENT_PROVIDER:
  * "vnpay" (mặc định): VNPay Sandbox (xem vnpay.py). Hệ thống dựng URL thanh toán có ký HMAC-SHA512 rồi chuyển khách sang VNPay;
    kết quả về qua Return URL (khách quay lại) và IPN (VNPay gọi server), cùng đi qua lõi `_apply`. Hoàn tiền chỉ mô phỏng.
  * "sandbox": cổng giả lập trong dự án (trang /thanh-toan/sandbox/<mã>/), kết quả ký HMAC-SHA256; dùng khi chạy offline và cho test.

Quy tắc chung:
  * mỗi nhóm đơn chỉ có MỘT giao dịch đang hiệu lực (ràng buộc duy nhất trong cơ sở dữ liệu);
  * giữ kho 15 phút kể từ lúc đặt hàng thành công (OrderGroup.hold_until); thanh toán lại không kéo dài hạn;
  * mỗi giao dịch chỉ cập nhật đơn một lần (processed_at); kết quả trùng bị bỏ qua;
  * kết quả thành công đến muộn (đơn đã hủy / hết hạn / thanh toán bằng giao dịch khác) -> "Thanh toán muộn" + Chờ hoàn tiền;
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from . import vnpay
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
    """Hủy giao dịch và đơn chưa thanh toán đã quá hạn giữ kho."""
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
    return [o for o in Order.objects.filter(group=group).exclude(status__in=(Order.CANCELED, Order.FAILED)) if o.payment_status == Order.UNPAID]


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
        unpaid = [o for o in Order.objects.select_for_update().filter(group=group).exclude(status__in=(Order.CANCELED, Order.FAILED))
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
def _apply(first, status, amount, group_id=None, now=None, gateway_transaction_id=None, paid_at=None):
    """Đối chiếu số tiền và cập nhật đơn đúng một lần.
    Trả về (kết_quả, giao_dịch); kết_quả in THANH_CONG | THAT_BAI | BO_QUA | THANH_TOAN_MUON."""
    now = now or timezone.now()
    # Khách đã trả đúng hạn nhưng kết quả về trễ: không để bước hết hạn hủy mất đơn của họ.
    hold = first.group.hold_until
    if not (paid_at and hold and paid_at <= hold):
        expire_overdue(now, group_id=first.group_id)

    with transaction.atomic():
        OrderGroup.objects.select_for_update().get(pk=first.group_id)
        txn = PaymentTransaction.objects.select_for_update(of=("self",)).select_related("group__user").get(pk=first.pk)
        if (group_id is not None and str(txn.group_id) != str(group_id)) or int(txn.amount) != int(amount):
            raise PaymentError("Số tiền hoặc mã nhóm đơn không khớp giao dịch, kết quả bị từ chối.")
        if txn.processed_at is not None:
            return "BO_QUA", txn                     # mỗi giao dịch chỉ cập nhật đơn một lần

        user = txn.group.user
        if gateway_transaction_id and not txn.zp_trans_id:
            txn.zp_trans_id = int(gateway_transaction_id)

        if status != "SUCCESS":
            fields = ["gateway_status", "status", "zp_trans_id"]
            txn.gateway_status = str(status)[:12]
            if txn.status == PaymentTransaction.PENDING:
                txn.status = PaymentTransaction.FAILED
            txn.processed_at = now
            fields.append("processed_at")
            txn.save(update_fields=fields)
            return "THAT_BAI", txn

        txn.gateway_status = "SUCCESS"
        txn.processed_at = now
        orders = list(Order.objects.select_for_update(of=("self",)).select_related("shop__owner").filter(group_id=txn.group_id))
        unpaid = [o for o in orders if o.status not in (Order.CANCELED, Order.FAILED) and o.payment_status == Order.UNPAID]
        valid = txn.status == PaymentTransaction.PENDING and unpaid and sum(o.total for o in unpaid) == txn.amount
        if not valid:
            txn.status = PaymentTransaction.LATE
            txn.refund_status = PaymentTransaction.REFUND_WAIT
            txn.save(update_fields=["gateway_status", "processed_at", "status", "refund_status", "zp_trans_id"])
            notify(user, f"Giao dịch {txn.ref} đến muộn, số tiền {vnd(txn.amount)} đang chờ hoàn tiền", "/don-hang/")
            return "THANH_TOAN_MUON", txn

        label = "VNPay" if txn.provider == PaymentTransaction.VNPAY else "cổng Sandbox"
        for o in unpaid:
            o.payment_status = Order.PAID
            o.payment_txn = txn
            o.save(update_fields=["payment_status", "payment_txn"])
            _log(o, o.status, o.status, None, f"Thanh toán thành công qua {label} ({txn.ref})")
            notify(user, f"Đơn hàng #{o.pk} đã thanh toán thành công", f"/don-hang/{o.pk}/")
            notify(o.shop.owner, f"Đơn hàng #{o.pk} đã được thanh toán, bạn có thể xác nhận đơn", f"/quan-ly/don-hang/{o.pk}/")
        txn.status = PaymentTransaction.SUCCESS
        txn.save(update_fields=["gateway_status", "processed_at", "status", "zp_trans_id"])
        return "THANH_CONG", txn


def process_result(params, now=None):
    """Cổng GIẢ LẬP: xác thực chữ ký HMAC rồi áp kết quả. Ném PaymentError khi chữ ký sai hoặc không khớp số tiền / mã giao dịch / mã nhóm đơn."""
    p = {k: str(params.get(k, "")) for k in SIGN_FIELDS}
    if not hmac.compare_digest(sign(p), str(params.get("sig", ""))):
        raise PaymentError("Chữ ký kết quả thanh toán không hợp lệ, kết quả bị từ chối.")
    first = PaymentTransaction.objects.select_related("group").filter(ref=p["txn_ref"]).first()
    if first is None:
        raise PaymentError("Không tìm thấy giao dịch thanh toán, kết quả bị từ chối.")
    if first.provider != PaymentTransaction.SANDBOX:
        raise PaymentError("Giao dịch này không thanh toán qua cổng giả lập, kết quả bị từ chối.")
    try:
        amount = int(p["amount"])
    except ValueError:
        raise PaymentError("Số tiền hoặc mã nhóm đơn không khớp giao dịch, kết quả bị từ chối.")
    return _apply(first, p["status"], amount, group_id=p["group"], now=now)


# =====================================================================================
#                                    VNPAY (SANDBOX)
# =====================================================================================
def _client_ip(request) -> str:
    ip = (request.META.get("REMOTE_ADDR") if request is not None else "") or ""
    return ip if ip and ":" not in ip else "127.0.0.1"          # VNPay chỉ nhận IPv4


def start_vnpay(txn: PaymentTransaction, request=None, now=None) -> str:
    """Dựng URL thanh toán VNPay cho giao dịch nội bộ `txn` (vnp_TxnRef = txn.ref) và trả về để chuyển hướng khách.
    Hạn thanh toán của VNPay (vnp_ExpireDate) = hạn giữ kho của nhóm đơn, nên thanh toán lại không kéo dài thêm hạn."""
    if not (settings.VNPAY_TMN_CODE and settings.VNPAY_HASH_SECRET):
        raise PaymentError("Chưa cấu hình VNPay: đặt VNPAY_TMN_CODE và VNPAY_HASH_SECRET trong file .env.")
    now = now or timezone.now()
    return_url = settings.VNPAY_RETURN_URL
    if not return_url and request is not None:
        return_url = request.build_absolute_uri(reverse("vnpay_return"))
    txn.provider = PaymentTransaction.VNPAY
    txn.order_url = vnpay.build_payment_url(
        settings.VNPAY_URL, settings.VNPAY_TMN_CODE, settings.VNPAY_HASH_SECRET, txn.ref, txn.amount,
        f"Thanh toan nhom don {txn.group_id}", return_url, _client_ip(request), now,
        max(txn.group.hold_until or now, now + timedelta(minutes=1)))
    txn.save(update_fields=["provider", "order_url"])
    return txn.order_url


def process_vnpay(params, now=None):
    """Return URL + IPN của VNPay: xác thực chữ ký, đối chiếu mã giao dịch + số tiền rồi áp kết quả qua `_apply`.
    Trả về (RspCode, Message, outcome, txn) - RspCode theo đặc tả IPN: 00 ok, 01 không thấy đơn, 02 đã xử lý, 04 sai tiền, 97 sai chữ ký.
    shortcut: không gọi API querydr của VNPay để đối soát; nếu khách đã trả mà cả Return URL lẫn IPN đều không tới
    (IPN cần URL công khai, vd. ngrok) thì đơn hết hạn giữ kho, nâng cấp khi cần chạy thật."""
    p = {k: str(v) for k, v in params.items() if k.startswith("vnp_")}
    if not vnpay.verify(p, settings.VNPAY_HASH_SECRET):
        return "97", "Invalid Checksum", None, None
    txn = PaymentTransaction.objects.select_related("group").filter(ref=p.get("vnp_TxnRef", ""), provider=PaymentTransaction.VNPAY).first()
    if txn is None:
        return "01", "Order not found", None, None
    try:
        raw = int(p["vnp_Amount"])
        if raw % 100:
            raise ValueError
    except (KeyError, ValueError):
        return "04", "Invalid amount", None, txn
    ok = vnpay.is_success(p)
    no = p.get("vnp_TransactionNo", "")
    try:
        outcome, txn = _apply(txn, "SUCCESS" if ok else (p.get("vnp_ResponseCode") or "ERR"), raw // 100, now=now,
                              gateway_transaction_id=no if ok and no.isdigit() else None,
                              paid_at=vnpay.parse_vn_date(p.get("vnp_PayDate")) if ok else None)
    except PaymentError:
        return "04", "Invalid amount", None, txn
    code, msg = ("02", "Order already confirmed") if outcome == "BO_QUA" else ("00", "Confirm Success")
    return code, msg, outcome, txn


# =====================================================================================
#                                   CẤU HÌNH CỔNG
# =====================================================================================
def provider() -> str:
    return getattr(settings, "PAYMENT_PROVIDER", "vnpay").lower()


def provider_label() -> str:
    return "VNPay Sandbox" if provider() == "vnpay" else "Sandbox giả lập"


def start_online_payment(txn: PaymentTransaction, request=None) -> str:
    """Sau create_payment: trả về địa chỉ cổng thanh toán."""
    if provider() == "vnpay":
        return start_vnpay(txn, request)
    if provider() == "sandbox":
        return reverse("sandbox_gateway", args=[txn.ref])
    raise PaymentError("Cổng thanh toán chưa được hỗ trợ.")


def refund_order(order_id, actor=None):
    """Ghi nhận hoàn tiền mô phỏng; giao dịch cũ của cổng khác cần xử lý bên ngoài."""
    from . import services
    order = Order.objects.select_related("payment_txn").filter(pk=order_id).first()
    if order is None:
        raise PaymentError("Không tìm thấy đơn cần hoàn tiền.")
    if order.payment_txn and order.payment_txn.provider not in (PaymentTransaction.SANDBOX, PaymentTransaction.VNPAY):
        raise PaymentError("Giao dịch cũ cần hoàn tiền qua cổng thanh toán trước khi cập nhật thủ công.")
    services.complete_refund(order_id, actor)
    return "DA_HOAN_TIEN"


def refund_late_transaction(txn_id, actor=None):
    """Ghi nhận hoàn tiền thủ công cho giao dịch đến muộn."""
    from . import services
    txn = PaymentTransaction.objects.filter(pk=txn_id).first()
    if txn is None:
        raise PaymentError("Không tìm thấy giao dịch cần hoàn tiền.")
    if txn.provider not in (PaymentTransaction.SANDBOX, PaymentTransaction.VNPAY):
        raise PaymentError("Giao dịch cũ cần hoàn tiền qua cổng thanh toán trước khi cập nhật thủ công.")
    services.complete_late_refund(txn_id, actor)
    return "DA_HOAN_TIEN"
