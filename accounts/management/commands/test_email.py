"""Kiểm tra cấu hình gửi email: python manage.py test_email ten@gmail.com  (in ra lỗi cụ thể nếu gửi thất bại)."""
import smtplib
import socket
import ssl

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Gửi một email thử tới địa chỉ chỉ định để kiểm tra cấu hình SMTP (Gmail)."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Địa chỉ nhận thư thử")

    def handle(self, *args, **opts):
        s = settings
        self.stdout.write(f"Backend : {s.EMAIL_BACKEND}")
        self.stdout.write(f"Máy chủ : {s.EMAIL_HOST}:{s.EMAIL_PORT}  TLS={s.EMAIL_USE_TLS}  SSL={getattr(s, 'EMAIL_USE_SSL', False)}")
        self.stdout.write(f"Tài khoản gửi: {s.EMAIL_HOST_USER or '(chưa đặt EMAIL_HOST_USER)'}  "
                          f"độ dài mật khẩu: {len(s.EMAIL_HOST_PASSWORD)} (mật khẩu ứng dụng Gmail phải đủ 16)")
        if "console" in s.EMAIL_BACKEND:
            self.stdout.write(self.style.WARNING("Đang dùng backend console: thư chỉ in ra terminal. Hãy đặt EMAIL_HOST_USER và EMAIL_HOST_PASSWORD."))
        try:
            n = send_mail("Shopphi - thư thử", "Cấu hình gửi email của Shopphi hoạt động.", None, [opts["to"]], fail_silently=False)
        except smtplib.SMTPAuthenticationError as e:
            self.stdout.write(self.style.ERROR(f"SAI XÁC THỰC: {e}\n -> Dùng 'Mật khẩu ứng dụng' 16 ký tự (không phải mật khẩu Gmail) và đã bật Xác minh 2 bước."))
        except (smtplib.SMTPServerDisconnected, ConnectionResetError, ssl.SSLError) as e:
            self.stdout.write(self.style.ERROR(f"BỊ NGẮT KẾT NỐI: {type(e).__name__}: {e}\n"
                " -> Thường do tường lửa/diệt virus (Kaspersky, Avast, ESET...: tắt 'quét email/SSL'), mạng trường/công ty chặn cổng 587,\n"
                "    hoặc sai cổng. Thử: $env:EMAIL_PORT='465'; $env:EMAIL_USE_SSL='1'  hoặc đổi sang mạng 4G/điện thoại."))
        except (socket.timeout, TimeoutError, socket.gaierror, OSError) as e:
            self.stdout.write(self.style.ERROR(f"KHÔNG KẾT NỐI ĐƯỢC: {type(e).__name__}: {e}\n -> Kiểm tra Internet / tường lửa chặn cổng {s.EMAIL_PORT}."))
        except Exception as e:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"LỖI KHÁC: {type(e).__name__}: {e}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Đã gửi {n} thư tới {opts['to']}. Kiểm tra hộp thư (cả Spam)."))
