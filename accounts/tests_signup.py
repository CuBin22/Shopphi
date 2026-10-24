"""Kiểm thử đăng ký bằng Gmail có xác nhận OTP qua email."""
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import otp
from accounts.models import Profile, SignupOTP

User = get_user_model()
EMAIL = "khach.moi@gmail.com"


def code_from_mail():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


@override_settings(OTP_RESEND_SECONDS=60, OTP_MAX_PER_HOUR=5, OTP_MAX_ATTEMPTS=5, OTP_TTL_MINUTES=10)
class SignupOtpTests(TestCase):
    def setUp(self):
        self.c = Client()

    def reg(self, ident=EMAIL, role="KHACH_HANG", pw="matkhau123"):
        return self.c.post(reverse("register"), {"full_name": "Lan", "identifier": ident, "role": role, "password": pw,
                                                 "password2": pw, "agree": "on", "default_address": "HCM"})

    def verify(self, code):
        return self.c.post(reverse("verify_register"), {"otp": code})

    def test_full_flow_creates_account_only_after_otp(self):
        r = self.reg()
        self.assertRedirects(r, reverse("verify_register"))
        self.assertEqual(User.objects.filter(username=EMAIL).count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        code = code_from_mail()
        row = SignupOTP.objects.get()
        self.assertNotIn(code, row.code_hash)                      # chỉ lưu băm
        r = self.verify(code)
        self.assertRedirects(r, reverse("login"))
        u = User.objects.get(username=EMAIL)
        self.assertEqual((u.email, u.first_name), (EMAIL, "Lan"))
        self.assertEqual(u.profile.role, Profile.CUSTOMER)
        self.assertEqual(u.profile.default_address, "HCM")
        self.assertTrue(u.check_password("matkhau123"))
        # đăng nhập được
        r = Client().post(reverse("login"), {"identifier": EMAIL, "password": "matkhau123"})
        self.assertEqual(r.status_code, 302)

    def test_vendor_role_kept(self):
        self.reg(role="NGUOI_BAN")
        self.verify(code_from_mail())
        self.assertEqual(User.objects.get(username=EMAIL).profile.role, Profile.VENDOR)

    def test_only_gmail_accepted(self):
        for bad in ("a@yahoo.com", "a@x.vn", "0912345678", "khong-phai-mail"):
            r = self.reg(bad)
            self.assertContains(r, "Gmail hợp lệ")
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(SignupOTP.objects.exists())

    def test_existing_gmail_rejected(self):
        User.objects.create_user(username=EMAIL, email=EMAIL, password="abc12345")
        self.assertContains(self.reg(), "đã có tài khoản")
        self.assertEqual(len(mail.outbox), 0)

    def test_password_rule_and_mismatch_still_enforced(self):
        self.assertContains(self.reg(pw="abcdefgh"), "gồm cả chữ và số")
        self.assertEqual(len(mail.outbox), 0)

    def test_wrong_code_does_not_create_and_locks_after_max_attempts(self):
        self.reg()
        good = code_from_mail()
        wrong = "000000" if good != "000000" else "111111"
        for _ in range(5):
            self.assertContains(self.verify(wrong), otp.BAD_OTP)
        self.assertContains(self.verify(good), otp.BAD_OTP)         # mã đúng cũng bị hủy sau 5 lần sai
        self.assertFalse(User.objects.filter(username=EMAIL).exists())

    def test_expired_code_rejected(self):
        self.reg()
        code = code_from_mail()
        SignupOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.verify(code), otp.BAD_OTP)
        self.assertFalse(User.objects.filter(username=EMAIL).exists())

    def test_code_is_single_use(self):
        self.reg()
        code = code_from_mail()
        self.verify(code)
        # phiên đăng ký đã xóa; dù có dựng lại phiên, mã đã dùng không còn hiệu lực
        with self.assertRaises(otp.OtpError):
            otp.verify_signup_otp(EMAIL, code)

    def test_resend_invalidates_old_code_and_respects_cooldown(self):
        self.reg()
        old = code_from_mail()
        self.c.post(reverse("resend_register_otp"))                # quá nhanh: không gửi thêm
        self.assertEqual(len(mail.outbox), 1)
        SignupOTP.objects.update(created=timezone.now() - timedelta(seconds=61))
        self.c.post(reverse("resend_register_otp"))
        self.assertEqual(len(mail.outbox), 2)
        new = code_from_mail()
        if new != old:
            self.assertContains(self.verify(old), otp.BAD_OTP)
        self.assertRedirects(self.verify(new), reverse("login"))

    def test_resubmitting_form_within_cooldown_reuses_code_and_updates_info(self):
        self.reg(pw="matkhau123")
        code = code_from_mail()
        r = self.reg(pw="matkhau456")                              # sửa mật khẩu ngay: không bị chặn, không gửi mail mới
        self.assertRedirects(r, reverse("verify_register"))
        self.assertEqual(len(mail.outbox), 1)
        self.verify(code)
        self.assertTrue(User.objects.get(username=EMAIL).check_password("matkhau456"))

    def test_hourly_limit(self):
        now = timezone.now()
        for i in range(5):
            otp.request_signup_otp(EMAIL, now=now + timedelta(minutes=i * 2))
        with self.assertRaises(otp.OtpError):
            otp.request_signup_otp(EMAIL, now=now + timedelta(minutes=11))

    def test_mail_failure_shows_error_and_creates_nothing(self):
        from unittest import mock
        with mock.patch("accounts.otp.send_mail", side_effect=OSError("smtp down")):
            r = self.reg()
        self.assertContains(r, "Không gửi được email")
        self.assertFalse(User.objects.filter(username=EMAIL).exists())
        self.assertFalse(SignupOTP.objects.filter(used_at__isnull=True).exists())

    def test_verify_page_needs_pending_signup(self):
        self.assertRedirects(self.c.get(reverse("verify_register")), reverse("register"))

    def test_forgot_password_by_gmail_still_works_end_to_end(self):
        self.reg()
        self.verify(code_from_mail())
        c = Client()
        c.post(reverse("forgot_password"), {"identifier": EMAIL})
        code = code_from_mail()
        r = c.post(reverse("reset_password"), {"otp": code, "password": "moimatkhau9", "password2": "moimatkhau9"})
        self.assertRedirects(r, reverse("login"))
        self.assertEqual(Client().post(reverse("login"), {"identifier": EMAIL, "password": "moimatkhau9"}).status_code, 302)
