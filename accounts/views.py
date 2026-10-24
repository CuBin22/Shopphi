import math
from datetime import timedelta

<<<<<<< HEAD
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
=======
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

<<<<<<< HEAD
from . import otp
from .forms import (ChangePasswordForm, ForgotForm, LoginForm, PHONE_RE, ProfileForm, RegisterForm, ResetForm,
                    VerifySignupForm)
=======
from .forms import LoginForm, RegisterForm
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
from .models import Profile
from .utils import get_profile, merge_anonymous, normalize_identifier

User = get_user_model()
MAX_FAILS = 5
LOCK_MINUTES = 15


def _home_for(profile):
    if profile.role == Profile.CUSTOMER:
        return "home"
    return "manage_home"


<<<<<<< HEAD
SESSION_SIGNUP_KEY = "signup_pending"


def register(request):
    """Bước 1: nhập thông tin bằng Gmail -> gửi OTP. CHƯA tạo tài khoản; dữ liệu (mật khẩu đã băm) giữ trong session."""
=======
def register(request):
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None, initial={"role": Profile.CUSTOMER})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
<<<<<<< HEAD
        email = d["identifier"]
        sent = True
        try:
            otp.request_signup_otp(email)
        except otp.OtpWaitError:
            sent = False             # vừa gửi mã cách đây chưa lâu: dùng lại mã đó, chỉ cập nhật thông tin đăng ký
        except otp.OtpError as e:
            form.add_error(None, str(e))
            return render(request, "accounts/register.html", {"form": form})
        request.session[SESSION_SIGNUP_KEY] = {
            "email": email, "name": d["full_name"].strip(), "role": d["role"], "pw": make_password(d["password"]),
            "address": d["default_address"].strip()}
        messages.info(request, (f"Mã OTP đã được gửi tới {otp.mask(email)} (hiệu lực {settings.OTP_TTL_MINUTES} phút)."
                                if sent else "Mã OTP đã gửi trước đó vẫn còn hiệu lực, hãy kiểm tra Gmail của bạn."))
        return redirect("verify_register")
    return render(request, "accounts/register.html", {"form": form})


def verify_register(request):
    """Bước 2: nhập mã OTP gửi qua Gmail; đúng mới tạo tài khoản."""
    if request.user.is_authenticated:
        return redirect("home")
    pending = request.session.get(SESSION_SIGNUP_KEY)
    if not pending:
        return redirect("register")
    form = VerifySignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = pending["email"]
        try:
            otp.verify_signup_otp(email, form.cleaned_data["otp"])
        except otp.OtpError as e:
            form.add_error("otp", str(e))
        else:
            if User.objects.filter(username=email).exists() or User.objects.filter(email__iexact=email).exists():
                request.session.pop(SESSION_SIGNUP_KEY, None)
                messages.error(request, "Gmail này đã có tài khoản. Hãy đăng nhập.")
                return redirect("login")
            with transaction.atomic():
                user = User(username=email, email=email, first_name=pending["name"], password=pending["pw"])
                user.save()
                Profile.objects.create(user=user, role=pending["role"], phone="", default_address=pending["address"])
            request.session.pop(SESSION_SIGNUP_KEY, None)
            messages.success(request, "Xác nhận Gmail và đăng ký thành công. Hãy đăng nhập." + (
                " Tài khoản Người bán cần đăng ký gian hàng và chờ Quản trị viên duyệt trước khi đăng bán."
                if pending["role"] == Profile.VENDOR else ""))
            return redirect("login")
    return render(request, "accounts/verify_register.html", {
        "form": form, "masked": otp.mask(pending["email"]), "resend_seconds": settings.OTP_RESEND_SECONDS})


@require_POST
def resend_register_otp(request):
    pending = request.session.get(SESSION_SIGNUP_KEY)
    if not pending:
        return redirect("register")
    try:
        otp.request_signup_otp(pending["email"])
        messages.info(request, f"Đã gửi lại mã OTP tới {otp.mask(pending['email'])}. Mã cũ hết hiệu lực.")
    except otp.OtpError as e:
        messages.error(request, str(e))
    return redirect("verify_register")


=======
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


>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
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
<<<<<<< HEAD


# ----------------------------------------------------------- quên mật khẩu (OTP)
SESSION_RESET_KEY = "reset_ident"


def forgot_password(request):
    """Bước 1: nhập email/SĐT đã đăng ký -> gửi OTP. Luôn hiện cùng một thông báo (không lộ tài khoản có tồn tại hay không)."""
    if request.user.is_authenticated:
        return redirect("home")
    form = ForgotForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ident = form.cleaned_data["identifier"]
        otp.request_otp(ident)
        request.session[SESSION_RESET_KEY] = ident
        messages.info(request, otp.sent_message())
        return redirect("reset_password")
    return render(request, "accounts/forgot.html", {"form": form})


def reset_password(request):
    """Bước 2: nhập mã OTP + mật khẩu mới."""
    if request.user.is_authenticated:
        return redirect("home")
    ident = request.session.get(SESSION_RESET_KEY)
    if not ident:
        return redirect("forgot_password")
    form = ResetForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            otp.reset_password(ident, d["otp"], d["password"])
        except otp.OtpError as e:
            form.add_error("otp", str(e))
        else:
            request.session.pop(SESSION_RESET_KEY, None)
            messages.success(request, "Đặt lại mật khẩu thành công. Hãy đăng nhập bằng mật khẩu mới.")
            return redirect("login")
    return render(request, "accounts/reset.html", {"form": form, "masked": otp.mask(ident),
                                                   "resend_seconds": settings.OTP_RESEND_SECONDS})


@require_POST
def resend_otp(request):
    ident = request.session.get(SESSION_RESET_KEY)
    if not ident:
        return redirect("forgot_password")
    otp.request_otp(ident)
    messages.info(request, otp.sent_message())
    return redirect("reset_password")


# ------------------------------------------------------------ tài khoản của tôi
@login_required
def profile(request):
    """Xem và sửa hồ sơ: họ tên, số điện thoại, địa chỉ nhận hàng mặc định (checkout dùng để điền sẵn)."""
    prof = get_profile(request.user)
    locked = bool(PHONE_RE.match(request.user.username))   # đăng nhập bằng số điện thoại
    initial = {"full_name": request.user.first_name, "phone": prof.phone or (request.user.username if locked else ""),
               "default_address": prof.default_address}
    form = ProfileForm(request.POST or None, initial=initial, user=request.user, phone_locked=locked)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        request.user.first_name = d["full_name"]
        request.user.save(update_fields=["first_name"])
        prof.default_address = d["default_address"].strip()
        if not locked:
            prof.phone = d["phone"]
        prof.save(update_fields=["default_address", "phone"])
        messages.success(request, "Đã cập nhật thông tin tài khoản.")
        return redirect("profile")
    return render(request, "accounts/profile.html", {"form": form, "profile": prof, "login_id": request.user.username})


@login_required
def change_password(request):
    """Đổi mật khẩu khi đã đăng nhập; giữ phiên hiện tại, các phiên khác hết hiệu lực."""
    form = ChangePasswordForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        request.user.set_password(form.cleaned_data["password"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        messages.success(request, "Đã đổi mật khẩu.")
        return redirect("profile")
    return render(request, "accounts/password_change.html", {"form": form})
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
