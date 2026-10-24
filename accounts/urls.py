from django.urls import path

from . import views

urlpatterns = [
    path("dang-ky/", views.register, name="register"),
<<<<<<< HEAD
    path("dang-ky/xac-nhan/", views.verify_register, name="verify_register"),
    path("dang-ky/gui-lai/", views.resend_register_otp, name="resend_register_otp"),
    path("dang-nhap/", views.login_view, name="login"),
    path("dang-xuat/", views.logout_view, name="logout"),
    path("tai-khoan/", views.profile, name="profile"),
    path("tai-khoan/doi-mat-khau/", views.change_password, name="change_password"),
    path("quen-mat-khau/", views.forgot_password, name="forgot_password"),
    path("quen-mat-khau/dat-lai/", views.reset_password, name="reset_password"),
    path("quen-mat-khau/gui-lai/", views.resend_otp, name="resend_otp"),
=======
    path("dang-nhap/", views.login_view, name="login"),
    path("dang-xuat/", views.logout_view, name="logout"),
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
]
