from .models import Category, Shop


def giao_dien(request):
    from accounts.utils import get_role
    from shopping.cart import Cart
    from shopping.models import Notification
    user = request.user
    ctx = {"nav_categories": Category.objects.all(), "role": None, "unread_count": 0}
    try:
        ctx["cart_count"] = Cart(request).count()
    except Exception:  # noqa: BLE001
        ctx["cart_count"] = 0
    if user.is_authenticated:
        ctx["role"] = get_role(user)
        ctx["unread_count"] = Notification.objects.filter(user=user, read=False).count()
        if ctx["role"] in ("NGUOI_BAN", "QUAN_TRI") and request.path.startswith("/quan-ly/"):
            ctx["side_badges"] = _side_badges(user, ctx["role"])
            if ctx["role"] == "NGUOI_BAN":
                ctx["my_shop_name"] = Shop.objects.filter(owner=user).values_list("name", flat=True).first()
    return ctx


def _side_badges(user, role):
    """Số việc đang chờ hiển thị cạnh mục trên thanh bên (chỉ tính ở kênh quản lý)."""
    from shopping.models import CancelRequest, Order, PaymentTransaction
    try:
        if role == "QUAN_TRI":
            from .models import Shop
            return {
                "admin_shops": Shop.objects.filter(status=Shop.PENDING).count(),
                "refunds": (Order.objects.filter(payment_status=Order.REFUND_WAIT).count()
                            + PaymentTransaction.objects.filter(refund_status=PaymentTransaction.REFUND_WAIT).count()),
            }
        return {
            "vendor_orders": (Order.objects.filter(shop__owner=user, status=Order.PENDING).count()
                              + CancelRequest.objects.filter(order__shop__owner=user, result=CancelRequest.PENDING).count()),
        }
    except Exception:  # noqa: BLE001  - số nhắc việc không được làm hỏng trang
        return {}
