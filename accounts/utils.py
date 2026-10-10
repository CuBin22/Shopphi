import re
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Profile


def normalize_identifier(raw: str) -> str:
    """Email -> chữ thường; số điện thoại -> chỉ còn chữ số, dạng 0xxxxxxxxx (QĐ1: không trùng)."""
    s = (raw or "").strip().lower()
    compact = re.sub(r"[\s.\-()]", "", s)
    if re.fullmatch(r"\+?\d{9,12}", compact):
        if compact.startswith("+84"):
            compact = "0" + compact[3:]
        elif compact.startswith("84") and len(compact) == 11:
            compact = "0" + compact[2:]
        return compact
    return s


def get_profile(user):
    """Lấy hồ sơ; tài khoản tạo bằng createsuperuser chưa có hồ sơ thì tự gán vai trò Quản trị viên."""
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = Profile.objects.create(user=user, role=Profile.ADMIN if user.is_superuser else Profile.CUSTOMER)
    return profile


def get_role(user):
    if not user.is_authenticated:
        return None
    return get_profile(user).role


def role_required(*roles):
    """Chỉ cho phép các vai trò chỉ định (RBAC ở tầng back-end, NFR03)."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if get_role(request.user) not in roles:
                raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def merge_anonymous(old_session_key, user):
    """Gắn hành vi và hội thoại chatbot của phiên ẩn danh vào tài khoản. Lỗi không chặn đăng nhập (NV9)."""
    if not old_session_key:
        return
    try:
        from catalog.models import BehaviorLog
        from chatbot.models import ChatLog
        BehaviorLog.objects.filter(session_key=old_session_key, user__isnull=True).update(user=user)
        ChatLog.objects.filter(session_key=old_session_key, user__isnull=True).update(user=user)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("Không gắn được hành vi phiên ẩn danh", exc_info=True)
