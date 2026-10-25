"""Vòng đời vận đơn GHN, dùng khóa đơn hàng và mã tham chiếu ổn định để chống tạo trùng."""
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import ghn, services
from .models import Order, OrderGroup


def check_environment(order):
    if order.shipping_data.get("api_url") != settings.GHN_API_URL:
        raise services.OrderError("Đơn thuộc môi trường GHN khác. Không đổi Sandbox/Production khi còn đơn đang xử lý.")


def confirm_order(user, order_id):
    # PostgreSQL session lock survives the intent commit. A second confirmation
    # returns immediately; it cannot mistake another request's intent for timeout.
    # Negative advisory keys are reserved here for GHN order creation.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [-order_id])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise services.OrderError("Một yêu cầu xác nhận khác đang xử lý. Vui lòng tải lại đơn hàng.")
    try:
        return _confirm_order(user, order_id)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [-order_id])


def _confirm_order(user, order_id):
    # Lưu ý định trước HTTP. Nếu timeout/rollback, việc hủy bị chặn đến khi retry
    # cùng client_order_code nhận lại vận đơn cũ; không giả định timeout là chưa tạo.
    with transaction.atomic():
        order = services._lock_order(order_id)
        services._check_vendor(order, user)
        check_environment(order)
        if order.tracking_code:
            return order
        if order.status != Order.PENDING:
            raise services.OrderError("Chỉ tạo vận đơn khi đơn đang chờ xác nhận.")
        if order.group.payment_method == OrderGroup.ONLINE and order.payment_status != Order.PAID:
            raise services.OrderError("Đơn trực tuyến phải thanh toán trước khi tạo vận đơn GHN.")
        was_pending = order.ghn_creation_pending
        order.ghn_creation_pending = True
        order.save(update_fields=["ghn_creation_pending"])
    with transaction.atomic():
        order = services._lock_order(order_id)
        if order.tracking_code:
            return order
        snapshot = order.shipping_data
        payload = {k: v for k, v in snapshot.items() if k not in ("shop_id", "api_url")}
        payload.update(to_name=order.group.recipient_name, to_phone=order.group.recipient_phone,
                       to_address=order.group.address, payment_type_id=1,
                       required_note="CHOXEMHANGKHONGTHU",
                       cod_amount=int(order.total) if order.group.payment_method == OrderGroup.COD else 0)
        try:
            data = ghn.request("v2/shipping-order/create", payload, shop_id=snapshot["shop_id"])
        except ghn.GHNError as exc:
            if not was_pending and not exc.uncertain:
                order.ghn_creation_pending = False
                order.save(update_fields=["ghn_creation_pending"])
                # Commit việc gỡ cờ trước khi báo lỗi; không rollback lần ghi này.
                error = exc
            else:
                raise
        else:
            error = None
        if error is None:
            return _save_shipment(order, user, data)
    raise error


def _save_shipment(order, user, data):
    code = data.get("order_code") if isinstance(data, dict) else None
    if not isinstance(code, str) or not code or len(code) > 60:
        raise ghn.GHNError("GHN chưa trả mã vận đơn. Bấm xác nhận lại để lấy kết quả.")
    order.carrier, order.tracking_code = "GHN", code
    order.status, order.ghn_status = Order.CONFIRMED, "ready_to_pick"
    order.ghn_creation_pending = False
    order.save(update_fields=["carrier", "tracking_code", "status", "ghn_status", "ghn_creation_pending"])
    services._log(order, Order.PENDING, Order.CONFIRMED, user, f"Tạo vận đơn GHN {code}")
    services.notify(order.group.user, f"Đơn #{order.pk} đã xác nhận, vận đơn GHN {code}", f"/don-hang/{order.pk}/")
    return order


def detail(order):
    check_environment(order)
    data = ghn.request("v2/shipping-order/detail", {"order_code": order.tracking_code},
                       shop_id=order.shipping_data["shop_id"], method="GET")
    if (not isinstance(data, dict) or data.get("order_code") != order.tracking_code
            or str(data.get("shop_id")) != str(order.shipping_data["shop_id"])):
        raise ghn.GHNError("Thông tin vận đơn GHN không khớp cửa hàng.")
    return data


def cancel_shipment(order):
    data = detail(order)
    if data.get("status") == "cancel":
        return
    result = ghn.request("v2/switch-status/cancel", {"order_codes": [order.tracking_code]},
                         shop_id=order.shipping_data["shop_id"])
    if not isinstance(result, list) or not any(
            row.get("order_code") == order.tracking_code and row.get("result") is True
            for row in result if isinstance(row, dict)):
        raise ghn.GHNError("GHN chưa xác nhận hủy vận đơn; tồn kho được giữ nguyên. Hãy đồng bộ rồi thử lại.")


def sync_order(order_id):
    with transaction.atomic():
        order = services._lock_order(order_id)
        if not order.shipping_data or not order.tracking_code:
            raise services.OrderError("Đơn chưa có vận đơn GHN.")
        data = detail(order)  # Không dùng Status từ webhook để quyết định tiền/kho.
        status = data.get("status")
        try:
            updated = parse_datetime(data.get("updated_date", ""))
        except (ValueError, TypeError):
            updated = None
        if not isinstance(status, str) or not status or len(status) > 40 or not updated or timezone.is_naive(updated):
            raise ghn.GHNError("GHN trả trạng thái hoặc thời điểm cập nhật không hợp lệ.")
        if order.ghn_updated_at and updated <= order.ghn_updated_at:
            return order
        previous = order.ghn_status
        order.ghn_status, order.ghn_updated_at = status, updated
        order.save(update_fields=["ghn_status", "ghn_updated_at"])
        in_transit = {"picked", "storing", "transporting", "sorting", "delivering", "delivery_fail",
                      "waiting_to_return", "return", "return_transporting", "return_sorting",
                      "returning", "return_fail", "returned", "damage", "lost", "delivered"}
        if status in in_transit and order.status == Order.CONFIRMED:
            order.status, order.shipped_at = Order.SHIPPING, timezone.now()
            order.save(update_fields=["status", "shipped_at"])
            services._log(order, Order.CONFIRMED, Order.SHIPPING, None, f"GHN: {status}")
        elif status != previous:
            services._log(order, order.status, order.status, None, f"GHN: {status}")
        if status == "delivered" and order.status == Order.SHIPPING:
            services.complete_order(order.pk, ghn=True)
        elif status == "cancel" and order.status == Order.CONFIRMED:
            services.cancel_order(order.pk, None, "GHN xác nhận hủy vận đơn", _ghn_verified=True)
        elif status in ("returned", "damage", "lost") and status != previous:
            services.notify(order.shop.owner, f"Đơn #{order.pk}: GHN {status}. Cần kiểm tra hàng và xử lý hoàn tiền.",
                            f"/quan-ly/don-hang/{order.pk}/")
        order.refresh_from_db()
        return order
