"""Giao diện khách hàng (v6): danh sách đơn có lọc/tìm/phân trang, chi tiết đơn hàng, mua lại,
đánh giá của tôi, thông báo (đánh dấu đã đọc từng cái / tất cả).

Mọi truy vấn đều giới hạn theo tài khoản đang đăng nhập (NFR03): đơn của người khác trả 404.
"""
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.utils import role_required
from catalog import services as catalog_services
from catalog.models import BehaviorLog, Product, Shop

from . import payments, services
from .cart import Cart
from .models import Notification, Order, OrderGroup, OrderItem, Review

customer_only = role_required(Profile.CUSTOMER)

ORDERS_PER_PAGE = 10          # số nhóm đơn mỗi trang ở "Đơn hàng của tôi"
NOTES_PER_PAGE = 20
REVIEWS_PER_PAGE = 10
UNPAID = "cho_thanh_toan"     # tab ảo: đơn thanh toán trực tuyến chưa thanh toán và còn hiệu lực
FLOW = [Order.PENDING, Order.CONFIRMED, Order.SHIPPING, Order.DONE]


def _timeouts():
    try:
        services.run_timeouts()
    except Exception:  # noqa: BLE001
        pass


def _page_query(request, drop=("trang",)):
    q = request.GET.copy()
    for k in drop:
        q.pop(k, None)
    return q.urlencode()


def _unpaid_online(qs):
    """Đơn còn hiệu lực, thuộc nhóm thanh toán trực tuyến và chưa thanh toán."""
    return qs.filter(group__payment_method=OrderGroup.ONLINE, payment_status=Order.UNPAID).exclude(status=Order.CANCELED)


# ===================================================================== UC08
@customer_only
def my_orders(request):
    """Danh sách đơn theo nhóm đơn; lọc theo trạng thái (tab), tìm theo mã đơn / mã nhóm / tên sản phẩm."""
    payments.reconcile_user(request.user)       # chốt giao dịch ZaloPay còn chờ (phòng trang ZaloPay không chuyển về)
    _timeouts()
    user = request.user
    status = request.GET.get("trang_thai", "").strip()
    q = request.GET.get("q", "").strip()

    mine = Order.objects.filter(group__user=user)
    flt = mine
    if status == UNPAID:
        flt = _unpaid_online(flt)
    elif status in dict(Order.STATUS):
        flt = flt.filter(status=status)
    else:
        status = ""
    if q:
        cond = Q(items__product_name__icontains=q) | Q(shop__name__icontains=q)
        digits = q.lstrip("#")
        if digits.isdigit():
            cond |= Q(pk=int(digits)) | Q(group_id=int(digits))
        flt = flt.filter(cond).distinct()

    group_ids = list(flt.order_by().values_list("group_id", flat=True).distinct())
    groups_qs = OrderGroup.objects.filter(pk__in=group_ids).order_by("-created", "-id").prefetch_related(
        Prefetch("orders", queryset=flt.select_related("shop").prefetch_related("items__variant__product__category")
                 .order_by("id").distinct(), to_attr="shown"))
    page = Paginator(groups_qs, ORDERS_PER_PAGE).get_page(request.GET.get("trang"))
    for g in page.object_list:
        g.can_pay = g.payment_method == OrderGroup.ONLINE and any(
            o.status != Order.CANCELED and o.payment_status == Order.UNPAID for o in g.shown)
        for o in g.shown:
            o.first_item = next(iter(o.items.all()), None)

    counts = dict(mine.values_list("status").annotate(n=Count("id")))
    tabs = [("", "Tất cả", sum(counts.values())),
            (UNPAID, "Chờ thanh toán", _unpaid_online(mine).count())]
    tabs += [(k, label, counts.get(k, 0)) for k, label in Order.STATUS]
    return render(request, "shopping/my_orders.html", {
        "page": page, "groups": page.object_list, "tabs": tabs, "status": status, "q": q,
        "page_query": _page_query(request), "provider_label": payments.provider_label(),
    })


def _steps(order, logs):
    """Các mốc tiến trình của đơn kèm thời điểm đạt được (lấy từ nhật ký trạng thái)."""
    at = {}
    for lg in logs:
        at.setdefault(lg.new_status, lg.at)
    label = dict(Order.STATUS)
    if order.status == Order.CANCELED:
        steps = [{"code": s, "label": label[s], "state": "done", "at": at.get(s)} for s in FLOW if s in at]
        steps.append({"code": Order.CANCELED, "label": label[Order.CANCELED], "state": "cancel", "at": at.get(Order.CANCELED)})
        return steps
    idx = FLOW.index(order.status)
    steps = []
    for i, s in enumerate(FLOW):
        state = "done" if i < idx or order.status == Order.DONE else "current" if i == idx else "todo"
        steps.append({"code": s, "label": label[s], "state": state, "at": at.get(s)})
    return steps


@customer_only
def order_detail(request, pk):
    """Chi tiết một đơn: tiến trình, sản phẩm, tiền, thanh toán, vận chuyển, yêu cầu hủy, nhật ký, đánh giá."""
    payments.reconcile_user(request.user)
    _timeouts()
    order = get_object_or_404(Order.objects.select_related("shop", "group", "shop_coupon", "group__global_coupon", "payment_txn"),
                              pk=pk, group__user=request.user)
    group = order.group
    items = list(order.items.select_related("variant__product__category", "variant__product__shop"))
    reviews = {r.product_id: r for r in Review.objects.filter(user=request.user, product_id__in=[i.variant.product_id for i in items])}
    can_reorder = False
    for i in items:
        p = i.product = i.variant.product
        i.review = reviews.get(p.pk)
        i.sellable = p.status == Product.VISIBLE and p.shop.status == Shop.ACTIVE
        i.in_stock = i.sellable and i.variant.stock > 0
        can_reorder = can_reorder or i.in_stock
    logs = list(order.status_logs.select_related("actor"))
    siblings = list(group.orders.exclude(pk=order.pk).select_related("shop").order_by("id"))
    online = group.payment_method == OrderGroup.ONLINE
    unpaid_in_group = [o for o in [order] + siblings if o.status != Order.CANCELED and o.payment_status == Order.UNPAID] if online else []
    txns = list(group.transactions.all()[:5]) if online else []
    pending = order.pending_cancel
    return render(request, "shopping/order_detail.html", {
        "o": order, "group": group, "items": items, "logs": logs, "steps": _steps(order, logs),
        "siblings": siblings, "requests": list(order.cancel_requests.all()), "pending": pending,
        "can_cancel": order.status in (Order.PENDING, Order.CONFIRMED) and not pending,
        "can_pay": online and order.status != Order.CANCELED and order.payment_status == Order.UNPAID,
        "pay_amount": sum(o.total for o in unpaid_in_group), "pay_orders": len(unpaid_in_group),
        "txns": txns, "online": online, "can_reorder": can_reorder,
        "provider_label": payments.provider_label(),
    })


@customer_only
@require_POST
def order_reorder(request, pk):
    """Mua lại: đưa các sản phẩm còn bán và còn hàng của đơn cũ vào giỏ (không vượt tồn kho)."""
    order = get_object_or_404(Order, pk=pk, group__user=request.user)
    cart = Cart(request)
    actor = catalog_services.get_actor(request)
    added, skipped = 0, []
    for item in order.items.select_related("variant__product__shop"):
        v = item.variant
        p = v.product
        if p.status != Product.VISIBLE or p.shop.status != Shop.ACTIVE:
            skipped.append(f"{item.product_name} (đã ngừng bán)")
            continue
        room = v.stock - cart.quantity_of(v.pk)
        if room <= 0:
            skipped.append(f"{item.product_name} (hết hàng hoặc giỏ đã đạt tối đa)")
            continue
        qty = min(item.qty, room)
        cart.set(v.pk, cart.quantity_of(v.pk) + qty)
        catalog_services.log_behavior(actor, BehaviorLog.ADD, p)
        added += 1
        if qty < item.qty:
            skipped.append(f"{item.product_name} (chỉ thêm {qty}/{item.qty} do tồn kho)")
    if added:
        messages.success(request, f"Đã thêm {added} sản phẩm của đơn #{order.pk} vào giỏ hàng.")
    if skipped:
        messages.warning(request, "Chưa thêm đủ: " + "; ".join(skipped) + ".")
    if not added and not skipped:
        messages.warning(request, "Đơn này không có sản phẩm nào để mua lại.")
    return redirect("cart") if added else redirect("order_detail", pk=order.pk)


# ===================================================================== UC10
@customer_only
def my_reviews(request):
    """Đánh giá của tôi: sản phẩm chờ đánh giá (đơn Hoàn thành, chưa đánh giá) và các đánh giá đã gửi."""
    user = request.user
    tab = request.GET.get("tab", "cho")
    reviewed_ids = set(Review.objects.filter(user=user).values_list("product_id", flat=True))
    pending, seen = [], set()
    for it in (OrderItem.objects.filter(order__group__user=user, order__status=Order.DONE)
               .select_related("order__shop", "variant__product__category").order_by("-order__created", "-order_id", "id")):
        pid = it.variant.product_id
        if pid in reviewed_ids or pid in seen:
            continue
        seen.add(pid)
        it.product = it.variant.product
        pending.append(it)
    mine = Review.objects.filter(user=user).select_related("product__category", "order").order_by("-created", "-id")
    page = Paginator(mine, REVIEWS_PER_PAGE).get_page(request.GET.get("trang"))
    return render(request, "shopping/my_reviews.html", {
        "tab": "da" if tab == "da" else "cho", "pending": pending, "page": page, "reviews": page.object_list,
        "n_reviewed": mine.count(), "page_query": _page_query(request),
    })


# ===================================================================== FR25
def _login_redirect(request):
    from django.contrib.auth.views import redirect_to_login
    return redirect_to_login(request.get_full_path())


def _safe_internal(link):
    """Chỉ cho chuyển hướng tới đường dẫn nội bộ của website."""
    return bool(link) and link.startswith("/") and not link.startswith("//") and "\\" not in link


def notifications(request):
    """Danh sách thông báo của chính mình. Không tự đánh dấu đã đọc: bấm vào thông báo hoặc nút "Đánh dấu tất cả"."""
    if not request.user.is_authenticated:
        return _login_redirect(request)
    only_unread = request.GET.get("chua_doc") == "1"
    qs = Notification.objects.filter(user=request.user)
    if only_unread:
        qs = qs.filter(read=False)
    page = Paginator(qs, NOTES_PER_PAGE).get_page(request.GET.get("trang"))
    unread_total = Notification.objects.filter(user=request.user, read=False).count()
    return render(request, "shopping/notifications.html", {
        "page": page, "items": page.object_list, "only_unread": only_unread, "unread_total": unread_total,
        "page_query": _page_query(request),
    })


def notification_open(request, pk):
    """Đánh dấu đã đọc rồi chuyển tới trang liên quan (nếu có)."""
    if not request.user.is_authenticated:
        return _login_redirect(request)
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if not n.read:
        n.read = True
        n.save(update_fields=["read"])
    return redirect(n.link if _safe_internal(n.link) else "notifications")


@require_POST
def notifications_read_all(request):
    if not request.user.is_authenticated:
        return _login_redirect(request)
    n = Notification.objects.filter(user=request.user, read=False).update(read=True)
    messages.success(request, f"Đã đánh dấu {n} thông báo là đã đọc." if n else "Không còn thông báo chưa đọc.")
    nxt = request.POST.get("next", "")
    ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})
    return redirect(nxt if nxt and ok else "notifications")
