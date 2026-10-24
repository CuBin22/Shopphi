"""Kiểm thử quên mật khẩu bằng OTP (email / SMS)."""
import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import otp, sms
from accounts.models import PasswordResetOTP, Profile

User = get_user_model()
SENT = []


def fake_sms(phone, text):
    SENT.append((phone, text))


def mk(ident, pw="abc12345"):
    u = User.objects.create_user(username=ident, password=pw, first_name="Khách", email=ident if "@" in ident else "")
    Profile.objects.create(user=u, role=Profile.CUSTOMER, phone="" if "@" in ident else ident)
    return u


def code_from_mail():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


@override_settings(SMS_BACKEND="accounts.tests.fake_sms", OTP_RESEND_SECONDS=60, OTP_MAX_PER_HOUR=5,
                   OTP_MAX_ATTEMPTS=5, OTP_TTL_MINUTES=10)
class PasswordResetTests(TestCase):
    def setUp(self):
        SENT.clear()
        self.u = mk("an@example.com")
        self.p = mk("0912345678")
        self.c = Client()

    def start(self, ident):
        r = self.c.post(reverse("forgot_password"), {"identifier": ident})
        self.assertRedirects(r, reverse("reset_password"))

    def finish(self, code, pw="matkhau123", pw2=None):
        return self.c.post(reverse("reset_password"), {"otp": code, "password": pw, "password2": pw2 or pw})

    # ------------------------------------------------------------ luồng chính
    def test_email_flow_resets_password_and_login_works(self):
        self.start("An@Example.com ")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["an@example.com"])
        r = self.finish(code_from_mail())
        self.assertRedirects(r, reverse("login"))
        self.assertTrue(Client().login(username="an@example.com", password="matkhau123"))
        self.assertFalse(Client().login(username="an@example.com", password="abc12345"))

    def test_sms_flow_for_phone_account(self):
        self.start("+84 912 345 678")
        self.assertEqual(len(mail.outbox), 0)
        phone, text = SENT[-1]
        self.assertEqual(phone, "0912345678")
        code = re.search(r"\b(\d{6})\b", text).group(1)
        self.assertRedirects(self.finish(code), reverse("login"))
        self.assertTrue(Client().login(username="0912345678", password="matkhau123"))

    def test_otp_is_stored_hashed_and_single_use(self):
        self.start("an@example.com")
        code = code_from_mail()
        row = PasswordResetOTP.objects.get()
        self.assertNotIn(code, (row.code_hash, row.salt))
        self.assertEqual(len(row.code_hash), 64)
        self.finish(code)
        s = self.c.session
        s["reset_ident"] = "an@example.com"                     # giả lập mở lại trang đặt lại
        s.save()
        r = self.finish(code, pw="khac123456")                  # dùng lại cùng mã
        self.assertContains(r, otp.BAD_OTP)
        self.assertTrue(Client().login(username="an@example.com", password="matkhau123"))

    # ------------------------------------------------------------ sai / hết hạn
    def test_wrong_code_counts_attempts_then_invalidates(self):
        self.start("an@example.com")
        good = code_from_mail()
        wrong = "000000" if good != "000000" else "111111"
        for _ in range(5):
            self.assertContains(self.finish(wrong), otp.BAD_OTP)
        self.assertContains(self.finish(good), otp.BAD_OTP)      # mã đúng cũng không còn dùng được
        self.assertTrue(Client().login(username="an@example.com", password="abc12345"))   # mật khẩu cũ giữ nguyên

    def test_expired_code_rejected(self):
        self.start("an@example.com")
        code = code_from_mail()
        PasswordResetOTP.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.finish(code), otp.BAD_OTP)

    def test_weak_password_does_not_consume_code(self):
        self.start("an@example.com")
        code = code_from_mail()
        r = self.finish(code, pw="12345678")
        self.assertContains(r, "gồm cả chữ và số")
        r = self.finish(code, pw="matkhau123", pw2="khac")
        self.assertContains(r, "không khớp")
        self.assertRedirects(self.finish(code), reverse("login"))

    def test_code_of_other_account_does_not_work(self):
        self.start("an@example.com")
        code = code_from_mail()
        s = self.c.session
        s["reset_ident"] = "0912345678"
        s.save()
        self.assertContains(self.finish(code), otp.BAD_OTP)
        self.assertEqual(self.p.check_password("abc12345"), True)

    # ------------------------------------------------------ không lộ tài khoản
    def test_unknown_account_same_response_and_nothing_sent(self):
        r1 = self.c.post(reverse("forgot_password"), {"identifier": "khongco@example.com"}, follow=True)
        r2 = self.c.post(reverse("forgot_password"), {"identifier": "an@example.com"}, follow=True)
        self.assertEqual(len(mail.outbox), 1)                   # chỉ tài khoản thật được gửi
        m1 = [str(m) for m in r1.context["messages"]]
        m2 = [str(m) for m in r2.context["messages"]]
        self.assertEqual(m1, m2)

    def test_unknown_account_cannot_reset(self):
        self.c.post(reverse("forgot_password"), {"identifier": "khongco@example.com"})
        self.assertContains(self.finish("123456"), otp.BAD_OTP)

    def test_invalid_identifier_format(self):
        r = self.c.post(reverse("forgot_password"), {"identifier": "abc"})
        self.assertContains(r, "email hợp lệ")

    def test_reset_page_requires_step_one(self):
        self.assertRedirects(Client().get(reverse("reset_password")), reverse("forgot_password"))

    # ------------------------------------------------------ giới hạn tần suất
    def test_cooldown_and_resend(self):
        self.start("an@example.com")
        self.c.post(reverse("resend_otp"))                      # quá nhanh: không gửi thêm
        self.assertEqual(len(mail.outbox), 1)
        PasswordResetOTP.objects.update(created=timezone.now() - timedelta(seconds=61))
        old = code_from_mail()
        self.c.post(reverse("resend_otp"))
        self.assertEqual(len(mail.outbox), 2)
        new = code_from_mail()
        if old != new:
            self.assertContains(self.finish(old), otp.BAD_OTP)  # mã cũ bị hủy khi gửi mã mới
        self.assertRedirects(self.finish(new), reverse("login"))

    def test_hourly_limit(self):
        now = timezone.now()
        for i in range(5):
            otp.request_otp("an@example.com", now=now + timedelta(minutes=i * 2))
        self.assertEqual(len(mail.outbox), 5)
        self.assertFalse(otp.request_otp("an@example.com", now=now + timedelta(minutes=11)))
        self.assertEqual(len(mail.outbox), 5)

    # ------------------------------------------------------ lỗi gửi và phụ trợ
    def test_delivery_failure_is_hidden_and_code_invalidated(self):
        with mock.patch("accounts.otp.send_mail", side_effect=OSError("smtp down")):
            self.assertFalse(otp.request_otp("an@example.com"))
        self.assertFalse(PasswordResetOTP.objects.filter(used_at__isnull=True).exists())

    def test_reset_clears_login_lock(self):
        prof = Profile.objects.get(user=self.u)
        prof.failed_logins, prof.locked_until = 3, timezone.now() + timedelta(minutes=10)
        prof.save()
        self.start("an@example.com")
        self.finish(code_from_mail())
        prof.refresh_from_db()
        self.assertEqual((prof.failed_logins, prof.locked_until), (0, None))

    def test_login_page_has_forgot_link(self):
        self.assertContains(self.c.get(reverse("login")), reverse("forgot_password"))

    def test_logged_in_user_redirected(self):
        self.c.login(username="an@example.com", password="abc12345")
        self.assertRedirects(self.c.get(reverse("forgot_password")), reverse("home"))

    def test_mask(self):
        self.assertEqual(otp.mask("an@example.com"), "a***@example.com")
        self.assertEqual(otp.mask("0912345678"), "091***78")


class SmsTests(TestCase):
    def test_e164(self):
        self.assertEqual(sms.to_e164_vn("0912345678"), "+84912345678")
        self.assertEqual(sms.to_e164_vn("84912345678"), "+84912345678")

    @override_settings(SMS_BACKEND="twilio", TWILIO_ACCOUNT_SID="AC1", TWILIO_AUTH_TOKEN="t", TWILIO_FROM="+1555")
    def test_twilio_request_shape(self):
        class R:
            def read(self): return b'{"sid":"SM1"}'
            def __enter__(self): return self
            def __exit__(self, *a): return False
        with mock.patch("urllib.request.urlopen", return_value=R()) as m:
            sms.send_sms("0912345678", "ma 123456")
        req = m.call_args[0][0]
        self.assertIn("/Accounts/AC1/Messages.json", req.full_url)
        self.assertIn(b"To=%2B84912345678", req.data)
        self.assertTrue(req.headers["Authorization"].startswith("Basic "))

    @override_settings(SMS_BACKEND="twilio", TWILIO_ACCOUNT_SID="", TWILIO_AUTH_TOKEN="", TWILIO_FROM="")
    def test_twilio_unconfigured_raises(self):
        with self.assertRaises(sms.SmsError):
            sms.send_sms("0912345678", "x")

    @override_settings(SMS_BACKEND="khong.ton.tai.ham")
    def test_bad_backend_raises(self):
        with self.assertRaises(sms.SmsError):
            sms.send_sms("0912345678", "x")
