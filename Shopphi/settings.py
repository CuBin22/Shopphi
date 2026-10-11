"""Cấu hình Django cho Shopphi (sàn TMĐT đa gian hàng).

Cấu hình kết nối PostgreSQL đọc từ biến môi trường (xem README.md):
DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-hay-doi-khi-trien-khai")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "catalog",
    "accounts",
    "shopping",
    "chatbot",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "accounts.middleware.IdleTimeoutMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "Shopphi.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.giao_dien",
            ],
        },
    },
]

WSGI_APPLICATION = "Shopphi.wsgi.application"
ASGI_APPLICATION = "Shopphi.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "Shopphi"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "22072005"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- Đăng nhập, phiên, chatbot ----
LOGIN_URL = "login"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14      # phiên ẩn danh giữ 14 ngày
IDLE_TIMEOUT_SECONDS = 30 * 60              # phiên đăng nhập hết hạn sau 30 phút không hoạt động (QĐ2)
CHATBOT_MODEL = os.environ.get("CHATBOT_MODEL", "claude-sonnet-5-5")   # dùng khi có ANTHROPIC_API_KEY

# ---- Thanh toán Sandbox (UC07) ----
# Khóa ký kết quả cổng thanh toán giả lập. Khi triển khai hãy đặt biến môi trường PAYMENT_SANDBOX_SECRET.
PAYMENT_SANDBOX_SECRET = os.environ.get("PAYMENT_SANDBOX_SECRET", "shopphi-sandbox-dev-secret-change-me")
PAYMENT_HOLD_MINUTES = 15

# ---- Thanh toán ZaloPay (Sandbox) ----
# PAYMENT_PROVIDER: "zalopay" (cổng ZaloPay Sandbox thật, mặc định) hoặc "sandbox" (cổng giả lập trong dự án, chạy offline).
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "zalopay").lower()
# Giá trị mặc định dưới đây là tài khoản DEMO công khai của ZaloPay (app_id 2553) để chạy thử ngay.
# Khi làm thật hãy đăng ký merchant Sandbox tại https://docs.zalopay.vn/ rồi đặt biến môi trường ZALOPAY_* của riêng bạn.
ZALOPAY_APP_ID = int(os.environ.get("ZALOPAY_APP_ID", "2553"))
ZALOPAY_KEY1 = os.environ.get("ZALOPAY_KEY1", "PcY4iZIKFCIdgZvA6ueMcMHHUbRLYjPL")   # ký yêu cầu tạo đơn / truy vấn / hoàn tiền
ZALOPAY_KEY2 = os.environ.get("ZALOPAY_KEY2", "kLtgPl8HHhfvMuDHPwKfgfsY4Ydm9eIz")   # xác thực callback ZaloPay gửi về
ZALOPAY_ENDPOINT = os.environ.get("ZALOPAY_ENDPOINT", "https://sb-openapi.zalopay.vn").rstrip("/")
ZALOPAY_TIMEOUT = int(os.environ.get("ZALOPAY_TIMEOUT", "10"))        # giây chờ khi gọi API ZaloPay
# URL công khai để ZaloPay gọi báo kết quả (cần https, ví dụ qua ngrok: https://xxxx.ngrok-free.app/thanh-toan/zalopay/callback/).
# Để trống: ZaloPay dùng callback URL đăng ký sẵn cho app; hệ thống vẫn nhận kết quả nhờ truy vấn khi khách quay lại + tác vụ đối soát.
ZALOPAY_CALLBACK_URL = os.environ.get("ZALOPAY_CALLBACK_URL", "")
# URL khách được chuyển về sau khi thanh toán. Để trống: tự dựng từ địa chỉ đang truy cập (/thanh-toan/zalopay/ket-qua/).
ZALOPAY_REDIRECT_URL = os.environ.get("ZALOPAY_REDIRECT_URL", "")
# Mã ngân hàng/hình thức: để trống = trang ZaloPay Gateway (QR đa năng, thẻ ATM, thẻ quốc tế); "zalopayapp" = mở app ZaloPay.
ZALOPAY_BANK_CODE = os.environ.get("ZALOPAY_BANK_CODE", "")
