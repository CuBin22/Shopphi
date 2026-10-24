from django.urls import path

from . import admin_views as a
<<<<<<< HEAD
from . import customer_views as cv
from . import manage_views as m
from . import product_views as pv
from . import vendor_views as vv
=======
from . import manage_views as m
from . import product_views as pv
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
from . import views as v

urlpatterns = [
    path("gio-hang/", v.cart, name="cart"),
    path("gio-hang/them/", v.cart_add, name="cart_add"),
    path("gio-hang/sua/", v.cart_update, name="cart_update"),
<<<<<<< HEAD
    path("mua-ngay/", v.buy_now, name="buy_now"),
    path("gio-hang/xoa/", v.cart_remove, name="cart_remove"),
    path("dat-hang/", v.checkout, name="checkout"),
    path("dat-hang/thanh-cong/<int:group_id>/", v.order_success, name="order_success"),
    path("don-hang/", cv.my_orders, name="my_orders"),
    path("don-hang/<int:pk>/", cv.order_detail, name="order_detail"),
    path("don-hang/<int:pk>/mua-lai/", cv.order_reorder, name="order_reorder"),
    path("don-hang/<int:pk>/huy/", v.order_cancel, name="order_cancel"),
    path("don-hang/<int:pk>/da-nhan/", v.order_received, name="order_received"),
    path("don-hang/<int:pk>/danh-gia/<int:product_id>/", v.review_create, name="review_create"),
    path("danh-gia-cua-toi/", cv.my_reviews, name="my_reviews"),
    path("thong-bao/", cv.notifications, name="notifications"),
    path("thong-bao/doc-tat-ca/", cv.notifications_read_all, name="notifications_read_all"),
    path("thong-bao/<int:pk>/", cv.notification_open, name="notification_open"),
    path("thanh-toan/<int:group_id>/", v.pay_group, name="pay_group"),
    path("thanh-toan/<int:group_id>/trang-thai/", v.payment_status, name="payment_status"),
    path("thanh-toan/sandbox/<str:ref>/", v.sandbox_gateway, name="sandbox_gateway"),
    path("thanh-toan/ket-qua/", v.payment_return, name="payment_return"),
    path("thanh-toan/vnpay/ipn/", v.vnpay_ipn, name="vnpay_ipn"),
    path("thanh-toan/vnpay/ket-qua/", v.vnpay_return, name="vnpay_return"),
=======
    path("gio-hang/xoa/", v.cart_remove, name="cart_remove"),
    path("dat-hang/", v.checkout, name="checkout"),
    path("dat-hang/thanh-cong/<int:group_id>/", v.order_success, name="order_success"),
    path("don-hang/", v.my_orders, name="my_orders"),
    path("don-hang/<int:pk>/", v.order_detail, name="order_detail"),
    path("don-hang/<int:pk>/huy/", v.order_cancel, name="order_cancel"),
    path("don-hang/<int:pk>/da-nhan/", v.order_received, name="order_received"),
    path("don-hang/<int:pk>/danh-gia/<int:product_id>/", v.review_create, name="review_create"),
    path("thong-bao/", v.notifications, name="notifications"),
    path("thanh-toan/<int:group_id>/", v.pay_group, name="pay_group"),
    path("thanh-toan/sandbox/<str:ref>/", v.sandbox_gateway, name="sandbox_gateway"),
    path("thanh-toan/ket-qua/", v.payment_return, name="payment_return"),
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
    path("thanh-toan/zalopay/callback/", v.zalopay_callback, name="zalopay_callback"),
    path("thanh-toan/zalopay/ket-qua/", v.zalopay_return, name="zalopay_return"),
    path("quan-ly/", m.manage_home, name="manage_home"),
    path("quan-ly/gian-hang/dang-ky/", m.shop_register, name="shop_register"),
    path("quan-ly/don-hang/", m.vendor_orders, name="vendor_orders"),
    path("quan-ly/don-hang/<int:pk>/", m.vendor_order_detail, name="vendor_order_detail"),
    path("quan-ly/ma-giam-gia/", m.coupons, name="coupons"),
    path("quan-ly/ma-giam-gia/<int:pk>/", m.coupon_detail, name="coupon_detail"),
    path("quan-ly/thong-ke/", m.stats_view, name="stats"),
    path("quan-ly/gian-hang/sua/", m.shop_edit, name="shop_edit"),
    # Người bán: sản phẩm (UC13)
    path("quan-ly/san-pham/", pv.product_list, name="product_list"),
    path("quan-ly/san-pham/them/", pv.product_form, name="product_add"),
    path("quan-ly/san-pham/<int:pk>/", pv.product_form, name="product_edit"),
    path("quan-ly/san-pham/<int:pk>/an-hien/", pv.product_toggle, name="product_toggle"),
    path("quan-ly/san-pham/<int:pk>/xoa/", pv.product_delete, name="product_delete"),
<<<<<<< HEAD
    path("quan-ly/kho/", pv.inventory, name="inventory"),
    path("quan-ly/danh-gia/", vv.vendor_reviews, name="vendor_reviews"),
    path("quan-ly/gian-hang/thong-tin/", vv.shop_info, name="shop_info"),
    path("quan-ly/don-hang/<int:pk>/phieu-giao/", vv.packing_slip, name="packing_slip"),
    path("quan-ly/ma-giam-gia/<int:pk>/sua/", vv.coupon_edit, name="coupon_edit"),
    path("quan-ly/ma-giam-gia/<int:pk>/tam-ngung/", vv.coupon_toggle, name="coupon_toggle"),
    path("quan-ly/ma-giam-gia/<int:pk>/xoa/", vv.coupon_delete, name="coupon_delete"),
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
    # Quản trị viên (UC16, UC17, UC18)
    path("quan-ly/duyet-gian-hang/", a.shops_review, name="admin_shops"),
    path("quan-ly/xu-ly-san-pham/", a.products_review, name="admin_products"),
    path("quan-ly/tu-khoa/", a.keywords_review, name="admin_keywords"),
    path("quan-ly/hoan-tien/", a.refunds, name="refunds"),
    path("quan-ly/nhat-ky/", a.admin_logs, name="admin_logs"),
]
