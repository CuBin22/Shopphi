import math
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, RegisterForm
from .models import Profile
from .utils import get_profile, merge_anonymous, normalize_identifier

User = get_user_model()
MAX_FAILS = 5
LOCK_MINUTES = 15


def _home_for(profile):
    if profile.role == Profile.CUSTOMER:
        return "home"
    return "manage_home"


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None, initial={"role": Profile.CUSTOMER})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        ident = d["identifier"]
        with transaction.atomic():
            user = User.objects.create_user(username=ident, password=d["password"], first_name=d["full_name"].strip(),
                                            email=ident if "@" in ident else "")
            Profile.objects.create(user=user, role=d["role"], phone="" if "@" in ident else ident,
                                   default_address=d["default_address"].strip())
        messages.success(request, "Đăng ký thành công. Hãy đăng nhập." + (
            " Tài khoản Người bán cần đăng ký gian hàng và chờ Quản trị viên duyệt trước khi đăng bán."
            if d["role"] == Profile.VENDOR else ""))
        return redirect("login")
    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = LoginForm(request.POST or None)
    nxt = request.POST.get("next") or request.GET.get("next", "")
    if request.method == "POST" and form.is_valid():
        ident = normalize_identifier(form.cleaned_data["identifier"])
        password = form.cleaned_data["password"]
        user = User.objects.filter(username=ident).first()
        profile = get_profile(user) if user else None
        now = timezone.now()
        if profile and profile.locked_until and profile.locked_until <= now:
            profile.locked_until, profile.failed_logins = None, 0
            profile.save(update_fields=["locked_until", "failed_logins"])
        if profile and profile.locked_until and profile.locked_until > now:
            minutes = max(1, math.ceil((profile.locked_until - now).total_seconds() / 60))
            form.add_error(None, f"Tài khoản đang tạm khóa đăng nhập, thử lại sau {minutes} phút.")
        else:
            auth_user = authenticate(request, username=ident, password=password)
            if auth_user is None:
                msg = "Sai thông tin đăng nhập."
                if profile:
                    profile.failed_logins += 1
                    if profile.failed_logins >= MAX_FAILS:
                        profile.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                        profile.failed_logins = 0
                        msg = f"Sai {MAX_FAILS} lần liên tiếp, tài khoản bị tạm khóa đăng nhập {LOCK_MINUTES} phút."
                    profile.save(update_fields=["failed_logins", "locked_until"])
                form.add_error(None, msg)
            else:
                old_key = request.session.session_key
                login(request, auth_user)
                profile.failed_logins, profile.locked_until = 0, None
                profile.save(update_fields=["failed_logins", "locked_until"])
                merge_anonymous(old_key, auth_user)
                if profile.role == Profile.CUSTOMER:
                    from shopping.cart import merge_session_cart
                    merge_session_cart(request, auth_user)
                messages.success(request, f"Xin chào {auth_user.first_name or auth_user.get_username()}!")
                if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
                    return redirect(nxt)
                return redirect(_home_for(profile))
    return render(request, "accounts/login.html", {"form": form, "next": nxt})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Bạn đã đăng xuất.")
    return redirect("home")
