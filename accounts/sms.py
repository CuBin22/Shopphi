"""Gửi SMS. Chọn nhà cung cấp bằng settings.SMS_BACKEND:
  * "console": in nội dung ra log và cửa sổ chạy server (mặc định, để chạy thử, KHÔNG gửi SMS thật);
  * "twilio":  gửi qua Twilio REST API (cần TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM);
  * "pkg.module.ham": hàm tự viết send(phone, text) để nối nhà cung cấp SMS Việt Nam (eSMS, SpeedSMS, ...).
Lỗi gửi được ném ra dưới dạng SmsError."""
import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


class SmsError(Exception):
    pass


def to_e164_vn(phone: str) -> str:
    """0912345678 -> +84912345678."""
    p = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    if p.startswith("+"):
        return p
    if p.startswith("84") and len(p) == 11:
        return "+" + p
    if p.startswith("0"):
        return "+84" + p[1:]
    return "+" + p


def _console(phone, text):
    logger.warning("[SMS giả lập] tới %s: %s", phone, text)
    print(f"\n[SMS giả lập] tới {phone}: {text}\n", flush=True)


def _twilio(phone, text):
    sid, token, sender = settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_FROM
    if not (sid and token and sender):
        raise SmsError("Chưa cấu hình TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM.")
    fields = {"To": to_e164_vn(phone), "Body": text}
    fields["MessagingServiceSid" if sender.startswith("MG") else "From"] = sender
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=urllib.parse.urlencode(fields).encode(), method="POST",
        headers={"Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode(),
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            body = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        raise SmsError(f"Twilio trả về HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise SmsError(f"Không gọi được Twilio: {e}") from e
    if body.get("error_code"):
        raise SmsError(f"Twilio từ chối: {body.get('message')}")


def send_sms(phone: str, text: str) -> None:
    backend = getattr(settings, "SMS_BACKEND", "console")
    if backend == "console":
        return _console(phone, text)
    if backend == "twilio":
        return _twilio(phone, text)
    try:
        func = import_string(backend)
    except ImportError as e:
        raise SmsError(f"SMS_BACKEND không hợp lệ: {backend}") from e
    try:
        func(phone, text)
    except SmsError:
        raise
    except Exception as e:  # noqa: BLE001
        raise SmsError(f"Nhà cung cấp SMS báo lỗi: {e}") from e
