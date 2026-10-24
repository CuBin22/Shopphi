"""Cấu hình Django cho Shopphi (sàn TMĐT đa gian hàng).

Cấu hình kết nối PostgreSQL đọc từ biến môi trường (xem README.md):
DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

<<<<<<< HEAD

def _load_dotenv(path):
    """Đọc file .env (KEY=VALUE mỗi dòng, bỏ dòng trống và dòng bắt đầu bằng #) vào os.environ.
    Biến môi trường đã đặt sẵn trong PowerShell luôn được ưu tiên. Không cần cài thêm thư viện."""
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        os.environ.setdefault(key.strip(), val)


_load_dotenv(BASE_DIR / ".env")        # chứa EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (không đưa vào git)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-hay-doi-khi-trien-khai")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]", ".ngrok-free.app"]
CSRF_TRUSTED_ORIGINS = ["https://*.ngrok-free.app"]   # chỉ dùng khi demo qua ngrok (IPN của VNPay)
=======
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-hay-doi-khi-trien-khai")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5

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

<<<<<<< HEAD
# ---- Thanh toán VNPay (Sandbox) ----
# Đăng ký merchant Sandbox miễn phí tại https://sandbox.vnpayment.vn/devreg/ (VNPay gửi TmnCode + HashSecret qua email), rồi đặt vào .env.
VNPAY_TMN_CODE = os.environ.get("VNPAY_TMN_CODE", "")
VNPAY_HASH_SECRET = os.environ.get("VNPAY_HASH_SECRET", "")
VNPAY_URL = os.environ.get("VNPAY_URL", "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html")
# Để trống: tự dựng từ địa chỉ đang truy cập (/thanh-toan/vnpay/ket-qua/). IPN (VNPay gọi server) cần URL công khai khai báo trong cổng quản trị VNPay: /thanh-toan/vnpay/ipn/
VNPAY_RETURN_URL = os.environ.get("VNPAY_RETURN_URL", "")

# ---- Thanh toán ZaloPay (Sandbox) ----
# PAYMENT_PROVIDER: "vnpay" (VNPay Sandbox, mặc định), "zalopay" (ZaloPay Sandbox) hoặc "sandbox" (cổng giả lập trong dự án, chạy offline).
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "vnpay").lower()
=======
# ---- Thanh toán ZaloPay (Sandbox) ----
# PAYMENT_PROVIDER: "zalopay" (cổng ZaloPay Sandbox thật, mặc định) hoặc "sandbox" (cổng giả lập trong dự án, chạy offline).
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "zalopay").lower()
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
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
<<<<<<< HEAD

# ---- Quên mật khẩu bằng OTP (email / SMS) ----
OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))          # mã OTP có hiệu lực bao lâu
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))         # nhập sai quá số lần này thì mã bị hủy
OTP_RESEND_SECONDS = int(os.environ.get("OTP_RESEND_SECONDS", "60"))    # khoảng cách tối thiểu giữa 2 lần gửi mã
OTP_MAX_PER_HOUR = int(os.environ.get("OTP_MAX_PER_HOUR", "5"))         # số mã tối đa gửi cho một tài khoản mỗi giờ

# Email: đặt EMAIL_HOST_USER + EMAIL_HOST_PASSWORD (Gmail: dùng "Mật khẩu ứng dụng", không dùng mật khẩu đăng nhập)
# thì gửi mail thật qua SMTP; để trống thì mã OTP được IN RA CỬA SỔ chạy runserver (tiện cho chạy thử).
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
# Cổng 587 + STARTTLS (mặc định). Nếu 587 bị chặn/ngắt kết nối: EMAIL_PORT=465 và EMAIL_USE_SSL=1.
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0") == "1"
EMAIL_USE_TLS = (os.environ.get("EMAIL_USE_TLS", "1") == "1") and not EMAIL_USE_SSL
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").replace(" ", "")   # mật khẩu ứng dụng hay bị dán kèm dấu cách
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "Shopphi <no-reply@shopphi.local>")
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST_USER else "django.core.mail.backends.console.EmailBackend")

# SMS: "console" (mặc định, in mã ra cửa sổ runserver), "twilio" (cần TWILIO_*), hoặc đường dẫn hàm tự viết
# dạng "myapp.sms.send" có chữ ký send(phone, text) để nối với nhà cung cấp SMS Việt Nam (eSMS, SpeedSMS, ...).
SMS_BACKEND = os.environ.get("SMS_BACKEND", "console")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")     # số gửi hoặc Messaging Service SID (bắt đầu bằng MG)

# ---- Ảnh sản phẩm ----
PRODUCT_IMAGE_MAX_BYTES = int(os.environ.get("PRODUCT_IMAGE_MAX_BYTES", str(3 * 1024 * 1024)))   # tối đa 3 MB mỗi ảnh
PRODUCT_IMAGE_MAX_COUNT = int(os.environ.get("PRODUCT_IMAGE_MAX_COUNT", "6"))                    # ảnh bìa + ảnh phụ
PRODUCT_IMAGE_MAX_SIDE = 1200                                                                    # cạnh dài tối đa sau khi chuẩn hóa (px)
PRODUCT_IMAGE_MIN_SIDE = 200                                                                     # cạnh ngắn tối thiểu (px)
LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))                            # "sắp hết hàng" khi tồn <= ngưỡng này
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
