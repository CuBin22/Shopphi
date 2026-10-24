"""Lớp VNPay (Sandbox/Production, API 2.1.0) - chỉ lo dựng URL và chữ ký, KHÔNG đụng cơ sở dữ liệu.

Khác ZaloPay: không có API "tạo đơn". Hệ thống tự dựng URL thanh toán có ký rồi chuyển hướng khách:
  * URL: {vnp_Url}?<tham số vnp_* sắp xếp theo tên, mã hóa quote_plus>&vnp_SecureHash=HMAC_SHA512(hash_secret, <chuỗi tham số>)
  * Kết quả về qua Return URL (khách quay lại) và IPN (VNPay gọi server): cùng cách ký, bỏ vnp_SecureHash khi tính lại.
  * Thành công khi vnp_ResponseCode == "00" và vnp_TransactionStatus == "00"; vnp_Amount = số tiền x 100.
TmnCode/HashSecret lấy từ settings (biến môi trường VNPAY_*), không nằm trong mã front-end (NFR04); không lưu thông tin thẻ (NFR02).
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone as dt_tz
from urllib.parse import quote_plus

VN_TZ = dt_tz(timedelta(hours=7))
DATE_FMT = "%Y%m%d%H%M%S"


def _query(params: dict) -> str:
    return "&".join(f"{k}={quote_plus(str(v))}" for k, v in sorted(params.items()))


def sign(params: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), _query(params).encode("utf-8"), hashlib.sha512).hexdigest()


def vn_date(dt) -> str:
    """yyyyMMddHHmmss theo giờ Việt Nam (GMT+7) - định dạng ngày bắt buộc của VNPay."""
    return dt.astimezone(VN_TZ).strftime(DATE_FMT)


def parse_vn_date(text):
    try:
        return datetime.strptime(str(text), DATE_FMT).replace(tzinfo=VN_TZ)
    except ValueError:
        return None


def build_payment_url(base_url, tmn_code, secret, txn_ref, amount, order_info, return_url, ip, create_at, expire_at) -> str:
    """URL thanh toán đã ký. order_info nên là tiếng Việt không dấu, không ký tự đặc biệt."""
    params = {
        "vnp_Version": "2.1.0", "vnp_Command": "pay", "vnp_TmnCode": tmn_code,
        "vnp_Amount": int(amount) * 100, "vnp_CurrCode": "VND", "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": order_info, "vnp_OrderType": "other", "vnp_Locale": "vn",
        "vnp_ReturnUrl": return_url, "vnp_IpAddr": ip,
        "vnp_CreateDate": vn_date(create_at), "vnp_ExpireDate": vn_date(expire_at),
    }
    return f"{base_url}?{_query(params)}&vnp_SecureHash={sign(params, secret)}"


def verify(params: dict, secret: str) -> bool:
    """Kết quả hợp lệ khi HMAC_SHA512 trên mọi tham số vnp_* (trừ vnp_SecureHash/vnp_SecureHashType) trùng vnp_SecureHash."""
    got = str(params.get("vnp_SecureHash", ""))
    data = {k: v for k, v in params.items() if k.startswith("vnp_") and k not in ("vnp_SecureHash", "vnp_SecureHashType")}
    return bool(got) and hmac.compare_digest(sign(data, secret).lower(), got.lower())


def is_success(params: dict) -> bool:
    return params.get("vnp_ResponseCode") == "00" and params.get("vnp_TransactionStatus") == "00"


if __name__ == "__main__":      # tự kiểm tra: python shopping/vnpay.py
    from urllib.parse import urlsplit, parse_qsl
    now = datetime.now(dt_tz.utc)
    url = build_payment_url("https://x/pay", "TMN", "SECRET", "TXN1", 180000, "Thanh toan nhom don 1",
                            "http://127.0.0.1:8000/r/", "127.0.0.1", now, now + timedelta(minutes=15))
    q = dict(parse_qsl(urlsplit(url).query))
    assert q["vnp_Amount"] == "18000000" and verify(q, "SECRET") and not verify(q, "KHAC")
    q["vnp_Amount"] = "100"
    assert not verify(q, "SECRET")                                  # sửa số tiền -> chữ ký sai
    assert parse_vn_date(vn_date(now)).replace(microsecond=0) == now.replace(microsecond=0)
    assert is_success({"vnp_ResponseCode": "00", "vnp_TransactionStatus": "00"}) and not is_success({"vnp_ResponseCode": "24"})
    print("vnpay.py OK")
