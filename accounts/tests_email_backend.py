"""Checks for HTTPS email delivery used on Render Free."""

import io
import json
from unittest import mock
from urllib.error import HTTPError

from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings

from accounts.email_backend import BrevoEmailBackend


@override_settings(
    EMAIL_BACKEND="accounts.email_backend.BrevoEmailBackend",
    BREVO_API_KEY="test-api-key",
    BREVO_SENDER_EMAIL="sender@example.com",
)
class BrevoEmailBackendTests(SimpleTestCase):
    @mock.patch("accounts.email_backend.urlopen")
    def test_sends_otp_over_https(self, open_url):
        open_url.return_value.__enter__.return_value.status = 201
        result = send_mail("OTP Shopphi", "Mã: 123456", None, ["buyer@example.com"])
        self.assertEqual(result, 1)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, BrevoEmailBackend.endpoint)
        self.assertEqual(request.get_header("Api-key"), "test-api-key")
        self.assertEqual(json.loads(request.data), {
            "sender": {"email": "sender@example.com", "name": "Shopphi"},
            "to": [{"email": "buyer@example.com"}],
            "subject": "OTP Shopphi",
            "textContent": "Mã: 123456",
        })

    @mock.patch("accounts.email_backend.urlopen")
    def test_api_error_is_not_reported_as_success(self, open_url):
        open_url.side_effect = HTTPError(BrevoEmailBackend.endpoint, 401, "Unauthorized", {}, io.BytesIO(b"invalid key"))
        with self.assertRaisesRegex(OSError, "Brevo API HTTP 401"):
            send_mail("OTP", "secret code", None, ["buyer@example.com"])

    @override_settings(BREVO_SENDER_EMAIL="")
    def test_missing_sender_is_an_error(self):
        with self.assertRaisesRegex(OSError, "BREVO_SENDER_EMAIL"):
            send_mail("OTP", "secret code", None, ["buyer@example.com"])
