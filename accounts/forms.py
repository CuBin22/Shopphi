import re

from django import forms
from django.contrib.auth import get_user_model

from .models import Profile
from .utils import normalize_identifier

User = get_user_model()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^0\d{9,10}$")
<<<<<<< HEAD
GMAIL_DOMAINS = ("gmail.com", "googlemail.com")


def is_gmail(ident):
    return bool(EMAIL_RE.match(ident)) and ident.rsplit("@", 1)[1] in GMAIL_DOMAINS


def validate_new_password(pw):
    """Quy tắc mật khẩu (QĐ1): tối thiểu 8 ký tự, gồm cả chữ và số. Dùng chung cho đăng ký và đặt lại mật khẩu."""
    if len(pw or "") < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise forms.ValidationError("Mật khẩu tối thiểu 8 ký tự, gồm cả chữ và số.")
    return pw
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5


class RegisterForm(forms.Form):
    """BM1 - Đăng ký tài khoản."""
    full_name = forms.CharField(label="Họ tên", max_length=80)
<<<<<<< HEAD
    identifier = forms.CharField(label="Gmail", max_length=150, widget=forms.EmailInput(
        attrs={"placeholder": "ten@gmail.com", "autocomplete": "email"}))
=======
    identifier = forms.CharField(label="Email hoặc số điện thoại", max_length=150)
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
    role = forms.ChoiceField(label="Loại tài khoản", choices=[(Profile.CUSTOMER, "Khách hàng"), (Profile.VENDOR, "Người bán")],
                             initial=Profile.CUSTOMER, widget=forms.RadioSelect)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput, strip=False)
    default_address = forms.CharField(label="Địa chỉ nhận hàng mặc định (không bắt buộc)", max_length=255, required=False)
    agree = forms.BooleanField(label="Tôi đồng ý với điều khoản sử dụng",
                               error_messages={"required": "Cần đồng ý điều khoản sử dụng mới tạo được tài khoản."})

    def clean_identifier(self):
        ident = normalize_identifier(self.cleaned_data["identifier"])
<<<<<<< HEAD
        if not is_gmail(ident):
            raise forms.ValidationError("Vui lòng nhập địa chỉ Gmail hợp lệ (dạng ten@gmail.com).")
        if User.objects.filter(username=ident).exists() or User.objects.filter(email__iexact=ident).exists():
            raise forms.ValidationError("Gmail này đã có tài khoản. Hãy đăng nhập.")
        return ident

    def clean_password(self):
        return validate_new_password(self.cleaned_data["password"])
=======
        if not (EMAIL_RE.match(ident) or PHONE_RE.match(ident)):
            raise forms.ValidationError("Nhập email hợp lệ hoặc số điện thoại 10-11 chữ số.")
        if User.objects.filter(username=ident).exists():
            raise forms.ValidationError("Email hoặc số điện thoại này đã có tài khoản. Hãy đăng nhập.")
        return ident

    def clean_password(self):
        pw = self.cleaned_data["password"]
        if len(pw) < 8 or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
            raise forms.ValidationError("Mật khẩu tối thiểu 8 ký tự, gồm cả chữ và số.")
        return pw
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Mật khẩu xác nhận không khớp.")
        return data


<<<<<<< HEAD
class VerifySignupForm(forms.Form):
    """Bước 2 của đăng ký - nhập mã OTP gửi qua Gmail."""
    otp = forms.CharField(label="Mã OTP (6 chữ số)", max_length=10)


=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
class LoginForm(forms.Form):
    """BM2 - Đăng nhập."""
    identifier = forms.CharField(label="Email hoặc số điện thoại", max_length=150)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, strip=False)
<<<<<<< HEAD


class ForgotForm(forms.Form):
    """Bước 1 - nhập email hoặc số điện thoại đã đăng ký."""
    identifier = forms.CharField(label="Email hoặc số điện thoại đã đăng ký", max_length=150)

    def clean_identifier(self):
        ident = normalize_identifier(self.cleaned_data["identifier"])
        if not (EMAIL_RE.match(ident) or PHONE_RE.match(ident)):
            raise forms.ValidationError("Nhập email hợp lệ hoặc số điện thoại 10-11 chữ số.")
        return ident


class ResetForm(forms.Form):
    """Bước 2 - nhập mã OTP và mật khẩu mới."""
    otp = forms.CharField(label="Mã OTP (6 chữ số)", max_length=10)
    password = forms.CharField(label="Mật khẩu mới", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Xác nhận mật khẩu mới", widget=forms.PasswordInput, strip=False)

    def clean_password(self):
        return validate_new_password(self.cleaned_data["password"])

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Mật khẩu xác nhận không khớp.")
        return data


class ProfileForm(forms.Form):
    """Hồ sơ tài khoản: họ tên, số điện thoại liên hệ, địa chỉ nhận hàng mặc định (dùng điền sẵn khi đặt hàng)."""
    full_name = forms.CharField(label="Họ tên", max_length=80)
    phone = forms.CharField(label="Số điện thoại", max_length=20, required=False)
    default_address = forms.CharField(label="Địa chỉ nhận hàng mặc định", max_length=255, required=False)

    def __init__(self, *args, user=None, phone_locked=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.phone_locked = phone_locked
        if phone_locked:   # tài khoản đăng ký bằng số điện thoại: số này là tên đăng nhập, không đổi ở đây
            self.fields["phone"].disabled = True

    def clean_full_name(self):
        name = self.cleaned_data["full_name"].strip()
        if not name:
            raise forms.ValidationError("Vui lòng nhập họ tên.")
        return name

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "")
        if self.phone_locked:
            return raw
        phone = normalize_identifier(raw)
        if not phone:
            return ""
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("Số điện thoại gồm 10-11 chữ số, bắt đầu bằng 0.")
        taken = (User.objects.filter(username=phone).exclude(pk=self.user.pk).exists()
                 or Profile.objects.filter(phone=phone).exclude(user=self.user).exists())
        if taken:
            raise forms.ValidationError("Số điện thoại này đã được tài khoản khác sử dụng.")
        return phone


class ChangePasswordForm(forms.Form):
    """Đổi mật khẩu khi đã đăng nhập: phải nhập đúng mật khẩu hiện tại; mật khẩu mới theo QĐ1."""
    old_password = forms.CharField(label="Mật khẩu hiện tại", widget=forms.PasswordInput, strip=False)
    password = forms.CharField(label="Mật khẩu mới", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Xác nhận mật khẩu mới", widget=forms.PasswordInput, strip=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_old_password(self):
        if not self.user.check_password(self.cleaned_data["old_password"]):
            raise forms.ValidationError("Mật khẩu hiện tại không đúng.")
        return self.cleaned_data["old_password"]

    def clean_password(self):
        return validate_new_password(self.cleaned_data["password"])

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Mật khẩu xác nhận không khớp.")
        if data.get("password") and data.get("old_password") and data["password"] == data["old_password"]:
            self.add_error("password", "Mật khẩu mới phải khác mật khẩu hiện tại.")
        return data
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
