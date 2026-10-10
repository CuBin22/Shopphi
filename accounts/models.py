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
