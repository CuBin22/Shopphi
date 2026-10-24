from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Hồ sơ mở rộng của tài khoản: vai trò (mỗi tài khoản đúng một vai trò) và trạng thái khóa đăng nhập."""
    ADMIN, VENDOR, CUSTOMER = "QUAN_TRI", "NGUOI_BAN", "KHACH_HANG"
    ROLES = [(ADMIN, "Quản trị viên"), (VENDOR, "Người bán"), (CUSTOMER, "Khách hàng")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("Vai trò", max_length=12, choices=ROLES, default=CUSTOMER)
    phone = models.CharField("Số điện thoại", max_length=20, blank=True)
    default_address = models.CharField("Địa chỉ nhận hàng mặc định", max_length=255, blank=True)
    failed_logins = models.PositiveSmallIntegerField("Số lần đăng nhập sai liên tiếp", default=0)
    locked_until = models.DateTimeField("Khóa đăng nhập đến", null=True, blank=True)

    class Meta:
        verbose_name = "Hồ sơ người dùng"
        verbose_name_plural = "Hồ sơ người dùng"

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"
<<<<<<< HEAD


class PasswordResetOTP(models.Model):
    """Mã OTP quên mật khẩu. Chỉ lưu BĂM của mã (HMAC với SECRET_KEY + muối), không lưu mã gốc.
    Mỗi mã dùng một lần, hết hạn sau OTP_TTL_MINUTES, nhập sai quá OTP_MAX_ATTEMPTS lần thì bị hủy."""
    EMAIL, SMS = "EMAIL", "SMS"
    CHANNELS = [(EMAIL, "Email"), (SMS, "SMS")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_otps")
    channel = models.CharField(max_length=5, choices=CHANNELS)
    destination = models.CharField("Nơi nhận", max_length=150)
    salt = models.CharField(max_length=32)
    code_hash = models.CharField(max_length=64)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField("Số lần nhập sai", default=0)
    used_at = models.DateTimeField("Đã dùng / hủy lúc", null=True, blank=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Mã OTP quên mật khẩu"
        verbose_name_plural = "Mã OTP quên mật khẩu"
        indexes = [models.Index(fields=["user", "-created"], name="ix_otp_user_created")]

    def __str__(self):
        return f"OTP {self.channel} cho {self.user_id} ({self.created:%d/%m %H:%M})"


class SignupOTP(models.Model):
    """Mã OTP xác nhận email khi đăng ký. Tài khoản CHỈ được tạo sau khi nhập đúng mã. Chỉ lưu BĂM của mã (HMAC + muối)."""
    email = models.CharField("Email đăng ký", max_length=150, db_index=True)
    salt = models.CharField(max_length=32)
    code_hash = models.CharField(max_length=64)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField("Số lần nhập sai", default=0)
    used_at = models.DateTimeField("Đã dùng / hủy lúc", null=True, blank=True)

    class Meta:
        ordering = ["-created", "-id"]
        verbose_name = "Mã OTP xác nhận đăng ký"
        verbose_name_plural = "Mã OTP xác nhận đăng ký"

    def __str__(self):
        return f"OTP đăng ký {self.email} ({self.created:%d/%m %H:%M})"
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
