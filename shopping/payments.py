"""Thanh toán trực tuyến (UC07, FR11, FR22, FR23, NFR02, NFR15).

Hai cổng, chọn bằng settings.PAYMENT_PROVIDER:
  * "zalopay" (mặc định): ZaloPay Sandbox thật (xem zalopay.py). Hệ thống tạo đơn bằng /v2/create rồi chuyển khách sang
    trang ZaloPay; kết quả về theo 3 đường: callback của ZaloPay (xác thực key2), truy vấn /v2/query khi khách quay lại,
    và đối soát nền trước khi hết hạn giữ kho. Cả 3 đều đi qua cùng một lõi `_apply` nên mỗi giao dịch chỉ cập nhật đơn một lần.
  * "sandbox": cổng giả lập trong dự án (trang /thanh-toan/sandbox/<mã>/), kết quả ký HMAC-SHA256; dùng khi chạy offline và cho test.

Quy tắc chung:
  * mỗi nhóm đơn chỉ có MỘT giao dịch đang hiệu lực (ràng buộc duy nhất trong cơ sở dữ liệu);
  * giữ kho 15 phút kể từ lúc đặt hàng thành công (OrderGroup.hold_until); thanh toán lại không kéo dài hạn;
  * mỗi giao dịch chỉ cập nhật đơn một lần (processed_at); kết quả trùng bị bỏ qua;
  * kết quả thành công đến muộn (đơn đã hủy / hết hạn / thanh toán bằng giao dịch khác) -> "Thanh toán muộn" + Chờ hoàn tiền;
  * không bao giờ nuốt tiền: giao dịch ZaloPay đã bị đánh dấu thất bại mà sau đó vẫn báo thành công thì cũng thành "Thanh toán muộn".
"""
import hashlib
import hmac
import json
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from . import zalopay
from .models import Order, OrderGroup, PaymentTransaction, RefundRecord
from .services import OrderError, _log, cancel_order, notify, vnd

logger = logging.getLogger(__name__)

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


def expire_overdue(now=None, group_id=None, reconcile=True) -> int:
    """Hủy giao dịch + đơn chưa thanh toán đã quá hạn giữ kho và hoàn trả tồn kho. Chạy lại không gây xử lý trùng.
    reconcile=True: với giao dịch ZaloPay còn chờ, hỏi ZaloPay (/v2/query) TRƯỚC khi hủy để không hủy nhầm đơn khách đã trả
    tiền nhưng callback bị lỡ."""
    now = now or timezone.now()
    qs = OrderGroup.objects.filter(payment_method=OrderGroup.ONLINE, hold_until__lte=now,
                                   orders__status=Order.PENDING, orders__payment_status=Order.UNPAID).distinct()
    if group_id is not None:
        qs = qs.filter(pk=group_id)
    total = 0
    for gid in list(qs.values_list("pk", flat=True)):
        if reconcile:
            reconcile_group(gid, now)
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
def _apply(first, status, amount, group_id=None, now=None, zp_trans_id=None, paid_at=None):
    """LÕI dùng chung cho mọi nguồn kết quả (cổng giả lập, callback ZaloPay, truy vấn ZaloPay).
    Chữ ký/MAC đã được xác thực ở nơi gọi. Ở đây đối chiếu số tiền + mã nhóm đơn (nếu có) và cập nhật đơn đúng một lần.
    status: "SUCCESS" hoặc giá trị khác = không thành công. paid_at: thời điểm ZaloPay ghi nhận tiền (nếu biết).
    Trả về (kết_quả, giao_dịch); kết_quả in THANH_CONG | THAT_BAI | BO_QUA | THANH_TOAN_MUON."""
    now = now or timezone.now()
    # Khách đã trả đúng hạn nhưng kết quả về trễ: không để bước hết hạn hủy mất đơn của họ.
    hold = first.group.hold_until
    if not (paid_at and hold and paid_at <= hold):
        expire_overdue(now, group_id=first.group_id, reconcile=False)

    with transaction.atomic():
        txn = PaymentTransaction.objects.select_for_update(of=("self",)).select_related("group__user").get(pk=first.pk)
        if (group_id is not None and str(txn.group_id) != str(group_id)) or int(txn.amount) != int(amount):
            raise PaymentError("Số tiền hoặc mã nhóm đơn không khớp giao dịch, kết quả bị từ chối.")
        if txn.processed_at is not None:
            return "BO_QUA", txn                     # mỗi giao dịch chỉ cập nhật đơn một lần

        user = txn.group.user
        if zp_trans_id and not txn.zp_trans_id:
            txn.zp_trans_id = int(zp_trans_id)

        if status != "SUCCESS":
            fields = ["gateway_status", "status", "zp_trans_id"]
            txn.gateway_status = str(status)[:12]
            if txn.status == PaymentTransaction.PENDING:
                txn.status = PaymentTransaction.FAILED
            if txn.provider != PaymentTransaction.ZALOPAY:
                # ZaloPay: KHÔNG khóa giao dịch bằng processed_at khi thất bại, vì khách có thể quay lại trả tiền cùng đơn.
                # Nếu về sau có kết quả thành công, giao dịch không còn Chờ thanh toán nên sẽ thành "Thanh toán muộn" -> hoàn tiền.
                txn.processed_at = now
                fields.append("processed_at")
            txn.save(update_fields=fields)
            return "THAT_BAI", txn

        txn.gateway_status = "SUCCESS"
        txn.processed_at = now
        orders = list(Order.objects.select_for_update(of=("self",)).select_related("shop__owner").filter(group_id=txn.group_id))
        unpaid = [o for o in orders if o.status != Order.CANCELED and o.payment_status == Order.UNPAID]
        valid = txn.status == PaymentTransaction.PENDING and unpaid and sum(o.total for o in unpaid) == txn.amount
        if not valid:
            txn.status = PaymentTransaction.LATE
            txn.refund_status = PaymentTransaction.REFUND_WAIT
            txn.save(update_fields=["gateway_status", "processed_at", "status", "refund_status", "zp_trans_id"])
            notify(user, f"Giao dịch {txn.ref} đến muộn, số tiền {vnd(txn.amount)} đang chờ hoàn tiền", "/don-hang/")
            return "THANH_TOAN_MUON", txn

        label = "ZaloPay" if txn.provider == PaymentTransaction.ZALOPAY else "cổng Sandbox"
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
    try:
        amount = int(p["amount"])
    except ValueError:
        raise PaymentError("Số tiền hoặc mã nhóm đơn không khớp giao dịch, kết quả bị từ chối.")
    return _apply(first, p["status"], amount, group_id=p["group"], now=now)


# =====================================================================================
#                                   ZALOPAY (SANDBOX)
# =====================================================================================
def provider() -> str:
    return getattr(settings, "PAYMENT_PROVIDER", "zalopay").lower()


def provider_label() -> str:
    return "ZaloPay Sandbox" if provider() == "zalopay" else "Sandbox giả lập"


def start_online_payment(txn: PaymentTransaction, request=None) -> str:
    """Sau create_payment: trả về địa chỉ để chuyển hướng khách (trang ZaloPay hoặc cổng giả lập)."""
    if provider() != "zalopay":
        return reverse("sandbox_gateway", args=[txn.ref])
    redirect_url = getattr(settings, "ZALOPAY_REDIRECT_URL", "")
    if not redirect_url and request is not None:
        redirect_url = request.build_absolute_uri(reverse("zalopay_return"))
    return start_zalopay(txn, redirect_url=redirect_url, callback_url=getattr(settings, "ZALOPAY_CALLBACK_URL", ""))


def _zalopay_items(txn):
    items = []
    for o in payable_orders(txn.group):
        items.append({"itemid": str(o.pk), "itemname": f"Don hang #{o.pk} - {o.shop.name}"[:100],
                      "itemprice": int(o.total), "itemquantity": 1})
    return items


def start_zalopay(txn: PaymentTransaction, redirect_url="", callback_url="", now=None) -> str:
    """Tạo đơn trên ZaloPay (/v2/create) cho giao dịch nội bộ `txn` và trả về order_url để chuyển hướng khách.
    app_trans_id = yymmdd_<mã giao dịch nội bộ> (duy nhất, yymmdd theo giờ Việt Nam) được lưu TRƯỚC khi gọi API để callback tìm lại được."""
    now = now or timezone.now()
    txn.provider = PaymentTransaction.ZALOPAY
    txn.app_trans_id = f"{zalopay.vn_date_prefix(now)}_{txn.ref}"
    txn.save(update_fields=["provider", "app_trans_id"])
    group = txn.group
    try:
        res = zalopay.create_order(
            app_trans_id=txn.app_trans_id, app_user=f"user{group.user_id}", amount=txn.amount,
            description=f"Shopphi - Thanh toán nhóm đơn #{group.pk}", items=_zalopay_items(txn),
            redirect_url=redirect_url, callback_url=callback_url)
    except zalopay.ZaloPayError as e:
        # Không có order_url nên khách không thể trả tiền; trả giao dịch về Thất bại để họ bấm thanh toán lại.
        # Không đặt processed_at: nếu ZaloPay thực ra đã nhận đơn (lỗi mạng giữa chừng) mà sau đó có tiền về thì vẫn thành "Thanh toán muộn" -> hoàn tiền.
        logger.warning("ZaloPay từ chối/không tạo được đơn cho %s: %s", txn.ref, e)
        txn.status = PaymentTransaction.FAILED
        txn.gateway_status = "ERR"
        txn.save(update_fields=["status", "gateway_status"])
        raise PaymentError(f"Không tạo được đơn thanh toán trên ZaloPay: {e}. Vui lòng thử lại.") from e
    txn.order_url = res["order_url"][:1000]
    txn.save(update_fields=["order_url"])
    return txn.order_url


# ------------------------------------------------------------ callback (ZaloPay -> hệ thống)
def _cb(code, message):
    return {"return_code": code, "return_message": message}


def process_zalopay_callback(raw_body, now=None) -> dict:
    """Xử lý callback ZaloPay gửi khi khách đã thanh toán thành công. Trả về JSON phản hồi cho ZaloPay:
    return_code 1 = đã nhận, 2 = trùng (đã xử lý trước đó), -1 = từ chối (sai MAC / không khớp), 0 = lỗi hệ thống (để ZaloPay gọi lại)."""
    try:
        body = json.loads(raw_body)
        data, mac = body["data"], body["mac"]
        if not isinstance(data, str) or not isinstance(mac, str):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return _cb(-1, "invalid request")
    if not zalopay.verify_callback(data, mac):
        logger.warning("Callback ZaloPay sai MAC")
        return _cb(-1, "mac not equal")
    try:
        d = json.loads(data)
        if int(d["app_id"]) != int(settings.ZALOPAY_APP_ID):
            return _cb(-1, "app_id not match")
        app_trans_id, amount = str(d["app_trans_id"]), int(d["amount"])
    except (ValueError, KeyError, TypeError):
        return _cb(-1, "invalid data")
    txn = PaymentTransaction.objects.select_related("group").filter(app_trans_id=app_trans_id).first()
    if txn is None:
        return _cb(-1, "app_trans_id not found")
    try:
        outcome, _ = _apply(txn, "SUCCESS", amount, now=now, zp_trans_id=d.get("zp_trans_id"),
                            paid_at=zalopay.ms_to_datetime(d.get("server_time")))
    except PaymentError as e:
        logger.error("Callback ZaloPay hợp lệ nhưng không khớp giao dịch %s: %s", txn.ref, e)
        return _cb(-1, "amount not match")
    except Exception:  # noqa: BLE001
        logger.exception("Lỗi xử lý callback ZaloPay cho %s", txn.ref)
        return _cb(0, "internal error")
    return _cb(2, "duplicated") if outcome == "BO_QUA" else _cb(1, "success")


# ----------------------------------------------- truy vấn / đối soát (hệ thống -> ZaloPay)
def sync_zalopay(txn: PaymentTransaction, now=None):
    """Hỏi ZaloPay (/v2/query) về giao dịch rồi áp kết quả qua cùng lõi `_apply`.
    Trả về (kết_quả, giao_dịch); kết_quả như _apply, thêm DANG_XU_LY khi ZaloPay chưa ghi nhận thanh toán.
    Ném PaymentError khi không gọi được ZaloPay."""
    if txn.provider != PaymentTransaction.ZALOPAY or not txn.app_trans_id:
        raise PaymentError("Giao dịch này không phải giao dịch ZaloPay.")
    try:
        res = zalopay.query_order(txn.app_trans_id)
    except zalopay.ZaloPayError as e:
        raise PaymentError(f"Không truy vấn được kết quả từ ZaloPay: {e}") from e
    code = res.get("return_code")
    if code == zalopay.RETURN_SUCCESS:
        try:
            amount = int(res.get("amount"))
        except (TypeError, ValueError):
            raise PaymentError("ZaloPay trả về số tiền không hợp lệ.")
        return _apply(txn, "SUCCESS", amount, now=now, zp_trans_id=res.get("zp_trans_id"),
                      paid_at=zalopay.ms_to_datetime(res.get("server_time")))
    if code == zalopay.RETURN_PROCESSING:
        return "DANG_XU_LY", txn
    return _apply(txn, "FAILED", int(txn.amount), now=now)


def reconcile_group(group_id, now=None):
    """Đối soát các giao dịch ZaloPay còn chờ của một nhóm đơn (dùng trước khi hủy vì hết hạn giữ kho)."""
    for txn in PaymentTransaction.objects.select_related("group").filter(
            group_id=group_id, status=PaymentTransaction.PENDING, provider=PaymentTransaction.ZALOPAY,
            app_trans_id__isnull=False):
        try:
            sync_zalopay(txn, now=now)
        except OrderError as e:
            logger.warning("Chưa đối soát được giao dịch %s: %s", txn.ref, e)


def reconcile_pending(now=None, min_age_seconds=60) -> int:
    """Tác vụ nền: đối soát mọi giao dịch ZaloPay còn chờ đã tạo hơn `min_age_seconds` (phòng callback bị lỡ). Trả về số giao dịch đã chốt."""
    now = now or timezone.now()
    done = 0
    for txn in PaymentTransaction.objects.select_related("group").filter(
            status=PaymentTransaction.PENDING, provider=PaymentTransaction.ZALOPAY, app_trans_id__isnull=False,
            created__lte=now - timedelta(seconds=min_age_seconds)):
        try:
            outcome, _ = sync_zalopay(txn, now=now)
            done += outcome in ("THANH_CONG", "THAT_BAI", "THANH_TOAN_MUON")
        except OrderError as e:
            logger.warning("Chưa đối soát được giao dịch %s: %s", txn.ref, e)
    return done


# ------------------------------------------------------------------ hoàn tiền (v2/refund)
def _finish_refund(rec: RefundRecord, res: dict):
    code = res.get("return_code")
    rec.message = (res.get("sub_return_message") or res.get("return_message") or "")[:255]
    if res.get("refund_id"):
        rec.zp_refund_id = int(res["refund_id"])
    rec.status = {zalopay.RETURN_SUCCESS: RefundRecord.SUCCESS,
                  zalopay.RETURN_PROCESSING: RefundRecord.PENDING}.get(code, RefundRecord.FAILED)
    rec.save(update_fields=["status", "message", "zp_refund_id", "updated"])
    return rec.status


def _zalopay_refund(txn: PaymentTransaction, order, amount, reason: str) -> str:
    """Hoàn tiền qua ZaloPay. Trả về RefundRecord.SUCCESS | PENDING | FAILED.
    Bản ghi RefundRecord được lưu TRƯỚC khi gọi API; đang có bản ghi Đang xử lý thì hỏi lại kết quả thay vì hoàn lần nữa."""
    if not txn.zp_trans_id:
        raise PaymentError("Giao dịch chưa có mã giao dịch ZaloPay (zp_trans_id) nên không hoàn tiền qua API được.")
    open_qs = RefundRecord.objects.filter(status__in=[RefundRecord.PENDING, RefundRecord.SUCCESS])
    open_qs = open_qs.filter(order=order) if order is not None else open_qs.filter(txn=txn, order__isnull=True)
    rec = open_qs.first()
    if rec is not None:
        if rec.status == RefundRecord.SUCCESS:
            return RefundRecord.SUCCESS
        try:                                    # đang xử lý: hỏi kết quả, không gửi hoàn tiền lần hai
            res = zalopay.query_refund(rec.m_refund_id)
        except zalopay.ZaloPayError as e:
            raise PaymentError(f"Không truy vấn được kết quả hoàn tiền từ ZaloPay: {e}") from e
        return _finish_refund(rec, res)
    try:
        with transaction.atomic():
            rec = RefundRecord.objects.create(txn=txn, order=order, amount=amount, m_refund_id=zalopay.new_refund_id())
    except IntegrityError:
        raise PaymentError("Đang có một yêu cầu hoàn tiền khác cho khoản này, vui lòng thử lại sau.")
    try:
        res = zalopay.refund(rec.m_refund_id, txn.zp_trans_id, amount, reason)
    except zalopay.ZaloPayError as e:
        # Không biết ZaloPay đã nhận hay chưa -> giữ Đang xử lý; lần bấm sau sẽ hỏi query_refund trước khi quyết định.
        rec.message = str(e)[:255]
        rec.save(update_fields=["message", "updated"])
        raise PaymentError(f"Chưa gửi được yêu cầu hoàn tiền tới ZaloPay: {e}. Bấm Hoàn tiền lần nữa để kiểm tra lại.") from e
    return _finish_refund(rec, res)


def refund_order(order_id, actor=None):
    """Hoàn tiền cho đơn đã thanh toán rồi bị hủy (Chờ hoàn tiền -> Đã hoàn tiền).
    Trả về "DA_HOAN_TIEN" hoặc "DANG_XU_LY" (ZaloPay đang xử lý). Giao dịch cổng giả lập: hoàn tiền mô phỏng như cũ."""
    from . import services
    order = Order.objects.select_related("payment_txn").filter(pk=order_id).first()
    if order is None:
        raise OrderError("Không tìm thấy đơn hàng.")
    if order.payment_status != Order.REFUND_WAIT:
        raise OrderError("Đơn này không ở trạng thái Chờ hoàn tiền.")
    txn = order.payment_txn
    if txn is None or txn.provider != PaymentTransaction.ZALOPAY:
        services.complete_refund(order_id, actor)
        return "DA_HOAN_TIEN"
    status = _zalopay_refund(txn, order, order.total, f"Shopphi - Hoan tien don #{order.pk}")
    if status == RefundRecord.SUCCESS:
        services.complete_refund(order_id, actor)
        return "DA_HOAN_TIEN"
    if status == RefundRecord.FAILED:
        rec = RefundRecord.objects.filter(order=order).first()
        raise PaymentError(f"ZaloPay từ chối hoàn tiền: {rec.message if rec else ''}. Có thể thử lại.")
    return "DANG_XU_LY"


def refund_late_transaction(txn_id, actor=None):
    """Hoàn tiền cho giao dịch Thanh toán muộn (hoàn toàn bộ số tiền của giao dịch)."""
    from . import services
    txn = PaymentTransaction.objects.filter(pk=txn_id).first()
    if txn is None or txn.refund_status != PaymentTransaction.REFUND_WAIT:
        raise OrderError("Giao dịch này không ở trạng thái Chờ hoàn tiền.")
    if txn.provider != PaymentTransaction.ZALOPAY:
        services.complete_late_refund(txn_id, actor)
        return "DA_HOAN_TIEN"
    status = _zalopay_refund(txn, None, txn.amount, f"Shopphi - Hoan tien giao dich {txn.ref}")
    if status == RefundRecord.SUCCESS:
        services.complete_late_refund(txn_id, actor)
        return "DA_HOAN_TIEN"
    if status == RefundRecord.FAILED:
        rec = RefundRecord.objects.filter(txn=txn, order__isnull=True).first()
        raise PaymentError(f"ZaloPay từ chối hoàn tiền: {rec.message if rec else ''}. Có thể thử lại.")
    return "DANG_XU_LY"
