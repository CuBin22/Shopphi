import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout


class IdleTimeoutMiddleware:
    """Phiên đăng nhập hết hạn sau 30 phút không hoạt động (QĐ2). Phiên ẩn danh không bị ảnh hưởng."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = time.time()
            last = request.session.get("last_activity")
            if last and now - last > settings.IDLE_TIMEOUT_SECONDS:
                logout(request)
                messages.warning(request, "Phiên đăng nhập đã hết hạn do không hoạt động quá 30 phút. Vui lòng đăng nhập lại.")
            else:
                request.session["last_activity"] = now
        return self.get_response(request)
