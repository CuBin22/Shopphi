"""Send transactional mail over HTTPS on hosts that block outbound SMTP."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoEmailBackend(BaseEmailBackend):
    endpoint = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        api_key = settings.BREVO_API_KEY
        sender = settings.BREVO_SENDER_EMAIL
        if not api_key or not sender:
            raise OSError("Chưa cấu hình BREVO_API_KEY hoặc BREVO_SENDER_EMAIL.")

        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            payload = {
                "sender": {"email": sender, "name": "Shopphi"},
                "to": [{"email": address} for address in message.recipients()],
                "subject": message.subject,
                "textContent": message.body,
            }
            request = Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:
                    if response.status != 201:
                        raise OSError(f"Brevo API trả về HTTP {response.status}.")
            except HTTPError as exc:
                detail = exc.read(500).decode("utf-8", errors="replace")
                if not self.fail_silently:
                    raise OSError(f"Brevo API HTTP {exc.code}: {detail}") from exc
                continue
            except (URLError, OSError):
                if not self.fail_silently:
                    raise
                continue
            sent += 1
        return sent
