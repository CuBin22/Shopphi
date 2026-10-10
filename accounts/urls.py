from django.urls import path

from . import views

urlpatterns = [
    path("dang-ky/", views.register, name="register"),
    path("dang-nhap/", views.login_view, name="login"),
    path("dang-xuat/", views.logout_view, name="logout"),
]
