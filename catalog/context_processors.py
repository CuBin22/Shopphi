from .models import Category


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
    return ctx
