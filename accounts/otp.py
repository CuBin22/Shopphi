"""Quên mật khẩu bằng OTP gửi tới email hoặc số điện thoại đã đăng ký (tên đăng nhập của hệ thống chính là email hoặc SĐT).

Bảo mật:
  * mã 6 chữ số sinh bằng `secrets`; chỉ lưu băm HMAC(SECRET_KEY, muối:mã); so sánh bằng compare_digest;
  * hiệu lực OTP_TTL_MINUTES, dùng một lần; sai quá OTP_MAX_ATTEMPTS lần thì hủy mã;
  * giới hạn tần suất gửi (cách nhau OTP_RESEND_SECONDS, tối đa OTP_MAX_PER_HOUR mã/giờ cho một tài khoản);
  * KHÔNG tiết lộ tài khoản có tồn tại hay không: mọi trường hợp đều trả cùng một thông điệp chung;
  * đặt lại mật khẩu thành công thì mọi mã khác bị hủy, phiên đăng nhập cũ hết hiệu lực (Django đổi session hash),
    và khóa đăng nhập do sai mật khẩu (QĐ2) được gỡ.
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .forms import EMAIL_RE, PHONE_RE, validate_new_password
from .models import PasswordResetOTP, Profile, SignupOTP
from .sms import SmsError, send_sms
from .utils import get_profile, normalize_identifier

User = get_user_model()
logger = logging.getLogger(__name__)

GENERIC_SENT = ("Nếu tài khoản tồn tại, mã OTP đã được gửi tới email/số điện thoại đã đăng ký "
                "(hiệu lực {ttl} phút). Chưa nhận được thì chờ {wait} giây rồi bấm Gửi lại mã.")
BAD_OTP = "Mã OTP không đúng hoặc đã hết hạn."


class OtpError(Exception):
    """Lỗi hiển thị trực tiếp cho người dùng (không làm lộ tài khoản có tồn tại hay không)."""


def sent_message():
    return GENERIC_SENT.format(ttl=settings.OTP_TTL_MINUTES, wait=settings.OTP_RESEND_SECONDS)


# --------------------------------------------------------------- tra cứu tài khoản
def find_account(raw):
    """Trả về (user, kênh, nơi_nhận) hoặc None. Email -> gửi mail; số điện thoại -> gửi SMS."""
    ident = normalize_identifier(raw)
    if EMAIL_RE.match(ident):
        user = User.objects.filter(Q(username=ident) | Q(email__iexact=ident)).first()
        return (user, PasswordResetOTP.EMAIL, ident) if user else None
    if PHONE_RE.match(ident):
        user = (User.objects.filter(username=ident).first()
                or User.objects.filter(profile__phone=ident).first())
        return (user, PasswordResetOTP.SMS, ident) if user else None
    return None


def mask(raw):
    """a***@gmail.com / 091***78: chỉ để hiển thị lại điều người dùng vừa nhập."""
    ident = normalize_identifier(raw)
    if "@" in ident:
        name, _, dom = ident.partition("@")
        return f"{name[:1]}***@{dom}"
    return f"{ident[:3]}***{ident[-2:]}" if len(ident) >= 6 else "***"


# ------------------------------------------------------------------- băm mã
def _hash(salt, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{salt}:{code}".encode(), hashlib.sha256).hexdigest()


def _new_code():
    return f"{secrets.randbelow(10 ** 6):06d}"


# --------------------------------------------------------------------- gửi mã
def _deliver(otp, code):
    ttl = settings.OTP_TTL_MINUTES
    if otp.channel == PasswordResetOTP.EMAIL:
        send_mail(
            subject="Shopphi - Mã OTP đặt lại mật khẩu",
            message=(f"Mã OTP đặt lại mật khẩu Shopphi của bạn là: {code}\n\n"
                     f"Mã có hiệu lực trong {ttl} phút và chỉ dùng được một lần.\n"
                     "Nếu bạn không yêu cầu, hãy bỏ qua email này và không chia sẻ mã cho bất kỳ ai."),
            from_email=None, recipient_list=[otp.destination], fail_silently=False)
    else:
        send_sms(otp.destination, f"Shopphi: ma OTP dat lai mat khau cua ban la {code}. Hieu luc {ttl} phut. Khong chia se ma nay.")


def request_otp(raw_identifier, now=None):
    """Tạo và gửi OTP. LUÔN trả về cùng một kết quả cho người gọi (không lộ tài khoản có tồn tại hay không);
    lý do thực sự (không có tài khoản, quá tần suất, lỗi gửi) chỉ ghi log. Trả về True nếu đã gửi mã đi."""
    now = now or timezone.now()
    found = find_account(raw_identifier)
    if found is None:
        return False
    user, channel, dest = found
    with transaction.atomic():
        recent = list(PasswordResetOTP.objects.select_for_update().filter(
            user=user, created__gte=now - timedelta(hours=1)).order_by("-created"))
        if recent and (now - recent[0].created).total_seconds() < settings.OTP_RESEND_SECONDS:
            logger.info("OTP cho user %s: bỏ qua vì gửi quá nhanh", user.pk)
            return False
        if len(recent) >= settings.OTP_MAX_PER_HOUR:
            logger.warning("OTP cho user %s: vượt %s mã/giờ", user.pk, settings.OTP_MAX_PER_HOUR)
            return False
        PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).update(used_at=now)   # mã cũ hết hiệu lực
        code, salt = _new_code(), secrets.token_hex(8)
        otp = PasswordResetOTP.objects.create(
            user=user, channel=channel, destination=dest, salt=salt, code_hash=_hash(salt, code),
            expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES))
    try:
        _deliver(otp, code)
    except (SmsError, OSError, Exception) as e:  # noqa: BLE001  (SMTP/SMS lỗi đủ loại)
        logger.error("Không gửi được OTP (%s) cho user %s: %s", channel, user.pk, e)
        PasswordResetOTP.objects.filter(pk=otp.pk).update(used_at=now)
        return False
    return True


# ------------------------------------------------------- xác thực và đặt lại mật khẩu
def reset_password(raw_identifier, code, new_password, now=None):
    """Kiểm tra OTP rồi đặt mật khẩu mới. Ném OtpError nếu mã sai/hết hạn hoặc mật khẩu không đạt (mã chưa bị tiêu hao)."""
    now = now or timezone.now()
    new_password = validate_new_password(new_password)          # ném ValidationError trước, không tiêu hao mã
    code = re.sub(r"\D", "", code or "")
    found = find_account(raw_identifier)
    if found is None:
        raise OtpError(BAD_OTP)
    user = found[0]
    failed = False
    with transaction.atomic():
        otp = (PasswordResetOTP.objects.select_for_update()
               .filter(user=user, used_at__isnull=True, expires_at__gt=now).order_by("-created").first())
        if otp is None or otp.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise OtpError(BAD_OTP)
        if len(code) != 6 or not hmac.compare_digest(_hash(otp.salt, code), otp.code_hash):
            # Ghi nhận lần sai rồi mới ném lỗi NGOÀI khối atomic: ném trong khối sẽ rollback bộ đếm và cho phép đoán mã vô hạn.
            otp.attempts += 1
            if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
                otp.used_at = now
            otp.save(update_fields=["attempts", "used_at"])
            failed = True
        else:
            user.set_password(new_password)
            user.save(update_fields=["password"])
            PasswordResetOTP.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
            profile = get_profile(user)
            profile.failed_logins, profile.locked_until = 0, None
            profile.save(update_fields=["failed_logins", "locked_until"])
    if failed:
        raise OtpError(BAD_OTP)
    return user


# =============================================================== OTP xác nhận đăng ký (Gmail)
class OtpWaitError(OtpError):
    """Gửi lại quá nhanh: người dùng phải chờ; mã đã gửi trước đó vẫn còn hiệu lực."""


def request_signup_otp(email, now=None):
    """Gửi mã OTP xác nhận tới `email` khi đăng ký. Khác quên mật khẩu, ở đây có thể báo lỗi rõ ràng cho người dùng
    (email chưa thuộc tài khoản nào nên không có gì để lộ). Ném OtpError nếu gửi quá nhanh/quá nhiều hoặc gửi mail thất bại."""
    now = now or timezone.now()
    with transaction.atomic():
        recent = list(SignupOTP.objects.select_for_update().filter(
            email=email, created__gte=now - timedelta(hours=1)).order_by("-created"))
        if recent:
            gap = (now - recent[0].created).total_seconds()
            if gap < settings.OTP_RESEND_SECONDS:
                raise OtpWaitError(f"Vui lòng chờ {int(settings.OTP_RESEND_SECONDS - gap) + 1} giây rồi gửi lại mã.")
        if len(recent) >= settings.OTP_MAX_PER_HOUR:
            raise OtpError("Bạn đã yêu cầu quá nhiều mã trong một giờ, vui lòng thử lại sau.")
        SignupOTP.objects.filter(email=email, used_at__isnull=True).update(used_at=now)     # mã cũ hết hiệu lực
        code, salt = _new_code(), secrets.token_hex(8)
        row = SignupOTP.objects.create(email=email, salt=salt, code_hash=_hash(salt, code),
                                       expires_at=now + timedelta(minutes=settings.OTP_TTL_MINUTES))
    try:
        send_mail(
            subject="Shopphi - Mã OTP xác nhận đăng ký tài khoản",
            message=(f"Mã OTP xác nhận đăng ký tài khoản Shopphi của bạn là: {code}\n\n"
                     f"Mã có hiệu lực trong {settings.OTP_TTL_MINUTES} phút và chỉ dùng được một lần.\n"
                     "Nếu bạn không đăng ký tài khoản, hãy bỏ qua email này và không chia sẻ mã cho bất kỳ ai."),
            from_email=None, recipient_list=[email], fail_silently=False)
    except Exception as e:  # noqa: BLE001  (SMTP lỗi đủ loại)
        logger.error("Không gửi được OTP đăng ký tới %s: %s", mask(email), e)
        SignupOTP.objects.filter(pk=row.pk).update(used_at=now)
        raise OtpError("Không gửi được email xác nhận. Hãy kiểm tra địa chỉ Gmail rồi thử lại sau ít phút.")


def verify_signup_otp(email, code, now=None):
    """Kiểm tra mã OTP đăng ký; đúng thì mã bị tiêu hao. Ném OtpError nếu sai/hết hạn/nhập sai quá số lần cho phép."""
    now = now or timezone.now()
    code = re.sub(r"\D", "", code or "")
    failed = False
    with transaction.atomic():
        row = (SignupOTP.objects.select_for_update()
               .filter(email=email, used_at__isnull=True, expires_at__gt=now).order_by("-created").first())
        if row is None or row.attempts >= settings.OTP_MAX_ATTEMPTS:
            raise OtpError(BAD_OTP)
        if len(code) != 6 or not hmac.compare_digest(_hash(row.salt, code), row.code_hash):
            row.attempts += 1                     # ghi nhận lần sai, ném lỗi NGOÀI khối atomic (xem reset_password)
            if row.attempts >= settings.OTP_MAX_ATTEMPTS:
                row.used_at = now
            row.save(update_fields=["attempts", "used_at"])
            failed = True
        else:
            SignupOTP.objects.filter(email=email, used_at__isnull=True).update(used_at=now)
    if failed:
        raise OtpError(BAD_OTP)
