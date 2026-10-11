"""Lớp gọi API ZaloPay (Sandbox/Production) - chỉ lo HTTP và chữ ký, KHÔNG đụng cơ sở dữ liệu.

Đặc tả theo "ZaloPay APIs Integration Document" (v2):
  * Tạo đơn   POST {endpoint}/v2/create          mac = HMAC_SHA256(key1, app_id|app_trans_id|app_user|amount|app_time|embed_data|item)
  * Truy vấn  POST {endpoint}/v2/query           mac = HMAC_SHA256(key1, app_id|app_trans_id|key1)
  * Hoàn tiền POST {endpoint}/v2/refund          mac = HMAC_SHA256(key1, app_id|zp_trans_id|amount|description|timestamp)
  * Truy vấn hoàn tiền POST {endpoint}/v2/query_refund   mac = HMAC_SHA256(key1, app_id|m_refund_id|timestamp)
  * Callback  ZaloPay -> hệ thống (JSON {data, mac, type}); hợp lệ khi HMAC_SHA256(key2, data) == mac

Khóa key1/key2 đọc từ settings (biến môi trường ZALOPAY_*), không nằm trong mã front-end (NFR04).
Hệ thống không nhận, không lưu thông tin thẻ: khách nhập thông tin thanh toán trực tiếp tại trang ZaloPay (NFR02).
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

RETURN_SUCCESS, RETURN_FAIL, RETURN_PROCESSING = 1, 2, 3


class ZaloPayError(Exception):
    """Lỗi khi gọi ZaloPay (mạng, phản hồi sai định dạng, hoặc ZaloPay từ chối). `code` là sub_return_code nếu có."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ tiện ích
def hmac_sha256(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def compact_json(obj) -> str:
    """JSON gọn, giữ nguyên tiếng Việt. Chuỗi này vừa gửi đi vừa đưa vào MAC nên phải dùng đúng một lần dựng."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def now_ms() -> int:
    return int(time.time() * 1000)


def vn_date_prefix(now=None) -> str:
    """yymmdd theo giờ Việt Nam (GMT+7) - bắt buộc đứng đầu app_trans_id."""
    return timezone.localtime(now or timezone.now()).strftime("%y%m%d")


def new_refund_id(now=None) -> str:
    """m_refund_id theo định dạng yymmdd_appid_xxxxxxxxxx (tối đa 45 ký tự)."""
    return f"{vn_date_prefix(now)}_{settings.ZALOPAY_APP_ID}_{secrets.randbelow(10 ** 10):010d}"


def ms_to_datetime(ms):
    from datetime import datetime, timezone as dt_tz
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=dt_tz.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# --------------------------------------------------------------------- HTTP
def _post(path: str, fields: dict) -> dict:
    """POST application/x-www-form-urlencoded, trả về JSON. Mọi lỗi mạng/định dạng đều đổi thành ZaloPayError."""
    url = settings.ZALOPAY_ENDPOINT + path
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=settings.ZALOPAY_TIMEOUT) as resp:  # noqa: S310 (URL cố định từ cấu hình)
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise ZaloPayError(f"ZaloPay trả về HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ZaloPayError(f"Không kết nối được ZaloPay: {e}") from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ZaloPayError("Phản hồi của ZaloPay không đúng định dạng JSON") from e
    if not isinstance(data, dict):
        raise ZaloPayError("Phản hồi của ZaloPay không đúng định dạng")
    return data


# ---------------------------------------------------------------- tạo đơn (v2/create)
def create_order_mac(app_id, app_trans_id, app_user, amount, app_time, embed_data, item) -> str:
    return hmac_sha256(settings.ZALOPAY_KEY1,
                       f"{app_id}|{app_trans_id}|{app_user}|{amount}|{app_time}|{embed_data}|{item}")


def create_order(app_trans_id, app_user, amount, description, items, redirect_url="", callback_url="",
                 bank_code=None, app_time=None) -> dict:
    """Tạo đơn trên ZaloPay. Trả về phản hồi (có order_url, zp_trans_token, order_token).
    Ném ZaloPayError nếu ZaloPay từ chối (return_code != 1) hoặc lỗi mạng."""
    app_id = settings.ZALOPAY_APP_ID
    app_time = app_time or now_ms()
    amount = int(amount)
    embed = {"redirecturl": redirect_url} if redirect_url else {}
    embed_data = compact_json(embed)
    item_json = compact_json(items)
    fields = {
        "app_id": app_id,
        "app_user": str(app_user)[:50],
        "app_trans_id": app_trans_id,
        "app_time": app_time,
        "amount": amount,
        "description": description[:256],
        "item": item_json,
        "embed_data": embed_data,
    }
    bank = settings.ZALOPAY_BANK_CODE if bank_code is None else bank_code
    if bank:
        fields["bank_code"] = bank
    if callback_url:
        fields["callback_url"] = callback_url
    fields["mac"] = create_order_mac(app_id, app_trans_id, fields["app_user"], amount, app_time, embed_data, item_json)

    res = _post("/v2/create", fields)
    if res.get("return_code") != RETURN_SUCCESS or not res.get("order_url"):
        raise ZaloPayError(res.get("sub_return_message") or res.get("return_message") or "ZaloPay từ chối tạo đơn",
                           code=res.get("sub_return_code"))
    return res


# ------------------------------------------------------------ truy vấn đơn (v2/query)
def query_order(app_trans_id: str) -> dict:
    """Hỏi ZaloPay trạng thái đơn. return_code: 1 = đã thanh toán, 2 = thất bại, 3 = đang xử lý / chưa thanh toán."""
    app_id = settings.ZALOPAY_APP_ID
    mac = hmac_sha256(settings.ZALOPAY_KEY1, f"{app_id}|{app_trans_id}|{settings.ZALOPAY_KEY1}")
    return _post("/v2/query", {"app_id": app_id, "app_trans_id": app_trans_id, "mac": mac})


# ------------------------------------------------------------------ callback
def verify_callback(data: str, mac: str) -> bool:
    """Callback hợp lệ khi HMAC_SHA256(key2, data) trùng mac do ZaloPay gửi."""
    expected = hmac_sha256(settings.ZALOPAY_KEY2, data)
    return hmac.compare_digest(expected, str(mac))


# ------------------------------------------------------------ hoàn tiền (v2/refund)
def refund(m_refund_id: str, zp_trans_id, amount, description: str, timestamp=None) -> dict:
    """Gửi yêu cầu hoàn tiền. return_code: 1 = thành công, 2 = thất bại, 3 = đang xử lý (dùng query_refund để biết kết quả)."""
    app_id = settings.ZALOPAY_APP_ID
    timestamp = timestamp or now_ms()
    amount = int(amount)
    description = description[:100]
    mac = hmac_sha256(settings.ZALOPAY_KEY1, f"{app_id}|{zp_trans_id}|{amount}|{description}|{timestamp}")
    return _post("/v2/refund", {
        "app_id": app_id, "m_refund_id": m_refund_id, "zp_trans_id": zp_trans_id,
        "amount": amount, "timestamp": timestamp, "description": description, "mac": mac})


def query_refund(m_refund_id: str, timestamp=None) -> dict:
    app_id = settings.ZALOPAY_APP_ID
    timestamp = timestamp or now_ms()
    mac = hmac_sha256(settings.ZALOPAY_KEY1, f"{app_id}|{m_refund_id}|{timestamp}")
    return _post("/v2/query_refund", {"app_id": app_id, "m_refund_id": m_refund_id, "timestamp": timestamp, "mac": mac})
