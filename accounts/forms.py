import re

from django import forms
from django.contrib.auth import get_user_model

from .models import Profile
from .utils import normalize_identifier

User = get_user_model()
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^0\d{9,10}$")


class RegisterForm(forms.Form):
    """BM1 - Đăng ký tài khoản."""
    full_name = forms.CharField(label="Họ tên", max_length=80)
    identifier = forms.CharField(label="Email hoặc số điện thoại", max_length=150)
    role = forms.ChoiceField(label="Loại tài khoản", choices=[(Profile.CUSTOMER, "Khách hàng"), (Profile.VENDOR, "Người bán")],
                             initial=Profile.CUSTOMER, widget=forms.RadioSelect)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label="Xác nhận mật khẩu", widget=forms.PasswordInput, strip=False)
    default_address = forms.CharField(label="Địa chỉ nhận hàng mặc định (không bắt buộc)", max_length=255, required=False)
    agree = forms.BooleanField(label="Tôi đồng ý với điều khoản sử dụng",
                               error_messages={"required": "Cần đồng ý điều khoản sử dụng mới tạo được tài khoản."})

    def clean_identifier(self):
        ident = normalize_identifier(self.cleaned_data["identifier"])
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

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password2") and data["password"] != data["password2"]:
            self.add_error("password2", "Mật khẩu xác nhận không khớp.")
        return data


class LoginForm(forms.Form):
    """BM2 - Đăng nhập."""
    identifier = forms.CharField(label="Email hoặc số điện thoại", max_length=150)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, strip=False)
