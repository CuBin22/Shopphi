"""Giao diện khách hàng: giỏ hàng, đặt hàng, theo dõi đơn, hủy đơn, đánh giá, thông báo."""
from django.conf import settings
from django.contrib import messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Profile
from accounts.utils import get_profile, get_role, role_required
from catalog import services as catalog_services
from catalog.models import BehaviorLog, Product, Shop, Variant

from urllib.parse import urlencode

from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import payments, services
from .cart import Cart
from .models import Notification, Order, OrderGroup, OrderItem, PaymentTransaction, Review
from .services import OrderError, build_checkout

customer_only = role_required(Profile.CUSTOMER)


def _safe_next(request, default):
    nxt = request.POST.get("next", "")
    ok = url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})
    return nxt if nxt and ok else default


def _int(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ giỏ hàng
def cart(request):
    catalog_services.get_actor(request)
    shops = Cart(request).grouped()
    return render(request, "shopping/cart.html", {"shops": shops, "grand": sum(s["subtotal"] for s in shops)})


@require_POST
def cart_add(request):
    actor = catalog_services.get_actor(request)
    variant = get_object_or_404(Variant.objects.select_related("product__shop"), pk=request.POST.get("variant"))
    product = variant.product
    back = _safe_next(request, product.get_absolute_url())
    if request.user.is_authenticated and get_role(request.user) != Profile.CUSTOMER:
        messages.error(request, "Chỉ tài khoản Khách hàng mới mua hàng. Người bán muốn mua hãy dùng tài khoản Khách hàng riêng.")
        return redirect(back)
    if product.status != Product.VISIBLE or product.shop.status != Shop.ACTIVE:
        messages.error(request, "Sản phẩm này đã ngừng bán.")
        return redirect(back)
    qty = max(1, _int(request.POST.get("qty"), 1))
    c = Cart(request)
    current = c.quantity_of(variant.pk)
    if variant.stock <= 0:
        messages.error(request, "Sản phẩm đã hết hàng, chưa thể thêm vào giỏ.")
    elif current + qty > variant.stock:
        messages.error(request, f"Chỉ còn {variant.stock} sản phẩm; trong giỏ của bạn đã có {current}.")
    else:
        c.set(variant.pk, current + qty)
        catalog_services.log_behavior(actor, BehaviorLog.ADD, product)
        messages.success(request, f"Đã thêm \"{product.name}\" vào giỏ hàng.")
    return redirect(back)


@require_POST
def cart_update(request):
    catalog_services.get_actor(request)
    variant = get_object_or_404(Variant, pk=request.POST.get("variant"))
    qty = _int(request.POST.get("qty"), 1)
    c = Cart(request)
    if qty < 1:
        messages.error(request, "Số lượng tối thiểu là 1. Muốn bỏ sản phẩm, chọn Xóa.")
    elif qty > variant.stock:
        messages.error(request, f"Số lượng vượt tồn kho, tối đa {variant.stock}.")
    elif c.quantity_of(variant.pk):
        c.set(variant.pk, qty)
    return redirect("cart")


@require_POST
def cart_remove(request):
    Cart(request).remove(_int(request.POST.get("variant"), 0))
    return redirect("cart")


# ------------------------------------------------------------------ đặt hàng
@customer_only
def checkout(request):
    cart_obj = Cart(request)
    lines = [{"v": l["v"], "qty": l["qty"]} for l in cart_obj.lines()]
    if not lines:
        messages.warning(request, "Giỏ hàng đang trống.")
        return redirect("cart")
    profile = get_profile(request.user)
    post = request.method == "POST"
    data = request.POST if post else {}
    g = lambda k, d="": (data.get(k, d) if post else d)  # noqa: E731
    info = {
        "name": g("name", request.user.first_name),
        "phone": g("phone", profile.phone),
        "address": g("address", profile.default_address),
    }
    method = g("payment_method", OrderGroup.COD)
    global_code = g("global_code").strip()
    shop_codes = {}
    for ln in lines:
        sid = ln["v"].product.shop_id
        shop_codes[sid] = g(f"coupon_{sid}").strip()
    co = build_checkout(lines, global_code, shop_codes)

    if post and data.get("action") == "place":
        try:
            group = services.place_order(request.user, {l["v"].pk: l["qty"] for l in lines}, info, method, global_code, shop_codes)
            messages.success(request, "Đặt hàng thành công.")
            return redirect("order_success", group_id=group.pk)
        except OrderError as e:
            messages.error(request, str(e))
    for p in co.parts:
        p.rows = [{"v": l["v"], "qty": l["qty"], "total": l["v"].price * l["qty"]} for l in p.lines]
        p.code = shop_codes.get(p.shop.pk, "")
        p.error = co.errors.get(f"shop_{p.shop.pk}")
    return render(request, "shopping/checkout.html", {
        "co": co, "info": info, "method": method, "global_code": global_code,
        "global_error": co.errors.get("global"), "shipping_fee": services.SHIPPING_FEE,
        "provider_label": payments.provider_label(), "hold_minutes": getattr(settings, "PAYMENT_HOLD_MINUTES", 15),
    })


@customer_only
def order_success(request, group_id):
    _timeouts()
    group = get_object_or_404(OrderGroup, pk=group_id, user=request.user)
    orders = list(group.orders.select_related("shop"))
    can_pay = group.payment_method == OrderGroup.ONLINE and any(
        o.status != Order.CANCELED and o.payment_status == Order.UNPAID for o in orders)
    return render(request, "shopping/order_success.html", {"group": group, "orders": orders, "can_pay": can_pay,
                                                           "provider_label": payments.provider_label()})


# --------------------------------------------------------------- theo dõi đơn
def _timeouts():
    try:
        services.run_timeouts()
    except Exception:  # noqa: BLE001
        pass


@customer_only
def my_orders(request):
    _timeouts()
    groups = OrderGroup.objects.filter(user=request.user).prefetch_related(
        Prefetch("orders", queryset=Order.objects.select_related("shop").prefetch_related("items"))).order_by("-created", "-id")
    return render(request, "shopping/my_orders.html", {"groups": groups})


@customer_only
def order_detail(request, pk):
    _timeouts()
    order = get_object_or_404(Order.objects.select_related("shop", "group"), pk=pk, group__user=request.user)
    items = list(order.items.select_related("variant__product"))
    reviewed = set(Review.objects.filter(user=request.user, product_id__in=[i.variant.product_id for i in items])
                   .values_list("product_id", flat=True))
    for i in items:
        i.product = i.variant.product
        i.reviewed = i.variant.product_id in reviewed
    return render(request, "shopping/order_detail.html", {
        "o": order, "items": items, "logs": order.status_logs.select_related("actor"),
        "requests": order.cancel_requests.all(), "pending": order.pending_cancel,
        "can_cancel": order.status in (Order.PENDING, Order.CONFIRMED) and not order.pending_cancel,
        "can_pay": order.group.payment_method == OrderGroup.ONLINE and order.status != Order.CANCELED
        and order.payment_status == Order.UNPAID,
        "provider_label": payments.provider_label(),
    })


@customer_only
@require_POST
def order_cancel(request, pk):
    try:
        result = services.customer_cancel(request.user, pk, request.POST.get("reason"))
        messages.success(request, "Đã hủy đơn hàng và hoàn trả tồn kho." if result == "DA_HUY"
                         else "Đã gửi yêu cầu hủy cho Người bán. Quá 24 giờ không phản hồi, yêu cầu sẽ tự được chấp nhận.")
    except OrderError as e:
        messages.error(request, str(e))
    return redirect("order_detail", pk=pk)


@customer_only
@require_POST
def order_received(request, pk):
    try:
        services.confirm_received(request.user, pk)
        messages.success(request, "Cảm ơn bạn! Đơn hàng đã hoàn thành, bạn có thể đánh giá sản phẩm.")
    except OrderError as e:
        messages.error(request, str(e))
    return redirect("order_detail", pk=pk)


@customer_only
@require_POST
def review_create(request, pk, product_id):
    try:
        services.create_review(request.user, pk, product_id, request.POST.get("rating"), request.POST.get("comment"))
        messages.success(request, "Đã gửi đánh giá. Cảm ơn bạn!")
    except OrderError as e:
        messages.error(request, str(e))
    return redirect("order_detail", pk=pk)


# ------------------------------------------------------------------ thông báo
def notifications(request):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    items = list(Notification.objects.filter(user=request.user)[:50])
    unread = [n.pk for n in items if not n.read]
    Notification.objects.filter(pk__in=unread).update(read=True)
    for n in items:
        n.was_unread = n.pk in unread
    return render(request, "shopping/notifications.html", {"items": items})


# ----------------------------------------------------- thanh toán trực tuyến (UC07)
@customer_only
@require_POST
def pay_group(request, group_id):
    """Tạo yêu cầu thanh toán cho cả nhóm đơn rồi chuyển hướng sang ZaloPay (hoặc cổng giả lập khi PAYMENT_PROVIDER=sandbox)."""
    try:
        txn = payments.create_payment(request.user, group_id)
        url = payments.start_online_payment(txn, request)
    except OrderError as e:
        messages.error(request, str(e))
        return redirect("order_success", group_id=group_id) if OrderGroup.objects.filter(pk=group_id, user=request.user).exists() \
            else redirect("my_orders")
    return redirect(url)


def sandbox_gateway(request, ref):
    """Cổng thanh toán GIẢ LẬP (Sandbox). Không nhận thông tin thẻ; chỉ cho chọn kết quả thử nghiệm."""
    txn = get_object_or_404(PaymentTransaction.objects.select_related("group"), ref=ref)
    if request.method == "POST":
        params = payments.build_callback(txn, request.POST.get("result", "cancel"))
        return redirect(reverse("payment_return") + "?" + urlencode(params))
    return render(request, "shopping/gateway.html", {"txn": txn, "stale": txn.status != PaymentTransaction.PENDING})


@csrf_exempt
def payment_return(request):
    """Nhận kết quả từ cổng (GET hoặc POST): xác thực chữ ký, đối chiếu số tiền / mã giao dịch / mã nhóm đơn."""
    params = request.GET if request.method == "GET" else request.POST
    back = redirect("my_orders") if request.user.is_authenticated else redirect("home")
    try:
        outcome, txn = payments.process_result(params)
    except OrderError as e:
        messages.error(request, str(e))
        return back
    text = {
        "THANH_CONG": (messages.success, "Thanh toán thành công (Sandbox). Người bán sẽ xác nhận đơn của bạn."),
        "THAT_BAI": (messages.warning, "Thanh toán không thành công hoặc đã hủy tại cổng. Bạn có thể thanh toán lại trong hạn giữ kho."),
        "BO_QUA": (messages.info, "Kết quả này đã được xử lý trước đó, đơn hàng không bị cập nhật lại."),
        "THANH_TOAN_MUON": (messages.warning, "Giao dịch đến muộn (đơn đã hủy hoặc đã thanh toán bằng giao dịch khác). "
                                              "Số tiền được chuyển sang Chờ hoàn tiền (mô phỏng)."),
    }[outcome]
    text[0](request, text[1])
    if request.user.is_authenticated and txn.group.user_id == request.user.pk:
        return redirect("order_success", group_id=txn.group_id)
    return back


# ------------------------------------------------------------------- ZaloPay
@csrf_exempt
@require_POST
def zalopay_callback(request):
    """ZaloPay gọi vào đây (server-to-server) khi khách đã thanh toán. Không cần đăng nhập, không dùng CSRF:
    tính xác thực nằm ở MAC (HMAC-SHA256 với key2). Phản hồi JSON theo đặc tả ZaloPay."""
    return JsonResponse(payments.process_zalopay_callback(request.body))


@require_GET
def zalopay_return(request):
    """Khách được ZaloPay chuyển về sau khi thanh toán/hủy. Không tin tham số trên URL: lấy mã giao dịch rồi hỏi lại ZaloPay
    bằng /v2/query (có ký key1) để biết kết quả thật."""
    back = redirect("my_orders") if request.user.is_authenticated else redirect("home")
    app_trans_id = request.GET.get("apptransid", "") or request.GET.get("app_trans_id", "")
    txn = PaymentTransaction.objects.select_related("group").filter(app_trans_id=app_trans_id).first() if app_trans_id else None
    if txn is None:
        messages.error(request, "Không xác định được giao dịch ZaloPay, vui lòng xem trạng thái tại Đơn hàng của tôi.")
        return back
    try:
        outcome, txn = payments.sync_zalopay(txn)
    except OrderError as e:
        messages.error(request, str(e))
        return back
    if outcome == "BO_QUA" and txn.status == PaymentTransaction.SUCCESS:
        outcome = "THANH_CONG"                 # callback đã xử lý trước khi khách quay về
    text = {
        "THANH_CONG": (messages.success, "Thanh toán ZaloPay thành công. Người bán sẽ xác nhận đơn của bạn."),
        "THAT_BAI": (messages.warning, "Thanh toán chưa thành công hoặc đã bị hủy tại ZaloPay. Bạn có thể thanh toán lại trong hạn giữ kho."),
        "DANG_XU_LY": (messages.info, "ZaloPay chưa ghi nhận thanh toán. Nếu bạn đã thanh toán, vui lòng chờ ít phút rồi tải lại; "
                                      "hệ thống sẽ tự đối soát."),
        "BO_QUA": (messages.info, "Kết quả này đã được xử lý trước đó, đơn hàng không bị cập nhật lại."),
        "THANH_TOAN_MUON": (messages.warning, "Giao dịch đến muộn (đơn đã hủy hoặc đã thanh toán bằng giao dịch khác). "
                                              "Số tiền được chuyển sang Chờ hoàn tiền."),
    }[outcome]
    text[0](request, text[1])
    if request.user.is_authenticated and txn.group.user_id == request.user.pk:
        return redirect("order_success", group_id=txn.group_id)
    return back
