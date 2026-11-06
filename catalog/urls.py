from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tim-kiem/", views.search, name="search"),
    path("shop/<int:pk>/", views.shop_detail, name="shop_detail"),
    path("api/goi-y-tu-khoa/", views.suggest, name="suggest"),
    path("san-pham/<slug:slug>/", views.product_detail, name="product"),
]
