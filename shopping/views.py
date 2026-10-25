"""Giao diện khách hàng: giỏ hàng, đặt hàng, theo dõi đơn, hủy đơn, đánh giá, thông báo."""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from accounts.models import Profile
from accounts.utils import get_profile, get_role, role_required
from catalog import services as catalog_services
from catalog.models import BehaviorLog, Product, Shop, Variant

from urllib.parse import urlencode

from django.urls import reverse
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from . import payments, services
from .cart import Cart
from .models import Order, OrderGroup, PaymentTransaction
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
    has_over = any(l["over"] for s in shops for l in s["lines"])
    return render(request, "shopping/cart.html", {"shops": shops, "grand": sum(s["subtotal"] for s in shops),
                                                  "has_over": has_over})


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


BUY_NOW_KEY = "buy_now"


@require_POST
def buy_now(request):
    """Mua ngay: không thêm vào giỏ, chuyển thẳng sang trang đặt hàng chỉ với sản phẩm (biến thể, số lượng) vừa chọn."""
    variant = get_object_or_404(Variant.objects.select_related("product__shop"), pk=request.POST.get("variant"))
    product = variant.product
    back = _safe_next(request, product.get_absolute_url())
    if not request.user.is_authenticated:
        messages.info(request, "Vui lòng đăng nhập bằng tài khoản Khách hàng để mua ngay.")
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(back)
    if get_role(request.user) != Profile.CUSTOMER:
        messages.error(request, "Chỉ tài khoản Khách hàng mới mua hàng. Người bán muốn mua hãy dùng tài khoản Khách hàng riêng.")
        return redirect(back)
    if product.status != Product.VISIBLE or product.shop.status != Shop.ACTIVE:
        messages.error(request, "Sản phẩm này đã ngừng bán.")
        return redirect(back)
    qty = max(1, _int(request.POST.get("qty"), 1))
    if variant.stock <= 0:
        messages.error(request, "Sản phẩm đã hết hàng, chưa thể mua.")
        return redirect(back)
    if qty > variant.stock:
        messages.error(request, f"Chỉ còn {variant.stock} sản phẩm, vui lòng giảm số lượng.")
        return redirect(back)
    request.session[BUY_NOW_KEY] = {"variant": variant.pk, "qty": qty, "back": product.get_absolute_url()}
    return redirect(reverse("checkout") + "?mua-ngay=1")


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
def _save_default_address(profile, info):
    """Khách tích "Lưu làm địa chỉ mặc định": cập nhật hồ sơ (số điện thoại chỉ điền khi hồ sơ chưa có)."""
    try:
        profile.default_address = info["address"].strip()[:255]
        fields = ["default_address"]
        if not profile.phone:
            profile.phone = info["phone"].strip()[:20]
            fields.append("phone")
        profile.save(update_fields=fields)
    except Exception:  # noqa: BLE001  - lỗi lưu địa chỉ không được làm hỏng đơn vừa đặt
        pass


@customer_only
def checkout(request):
    post = request.method == "POST"
    is_buy_now = (request.POST.get("mua_ngay") if post else request.GET.get("mua-ngay")) in ("1", 1)
    item = request.session.get(BUY_NOW_KEY) if is_buy_now else None
    if is_buy_now and not item:
        messages.warning(request, "Phiên mua ngay đã hết hạn, vui lòng chọn lại sản phẩm.")
        return redirect("cart")
    if is_buy_now:
        v = Variant.objects.select_related("product__shop", "product__category").filter(
            pk=item["variant"], product__status=Product.VISIBLE, product__shop__status=Shop.ACTIVE).first()
        if v is None:
            request.session.pop(BUY_NOW_KEY, None)
            messages.error(request, "Sản phẩm này đã ngừng bán.")
            return redirect("cart")
        if item["qty"] > v.stock:
            request.session.pop(BUY_NOW_KEY, None)
            messages.error(request, f"\"{v.product.name}\" ({v.name}) chỉ còn {v.stock} sản phẩm, vui lòng chọn lại số lượng.")
            return redirect(v.product.get_absolute_url())
        lines = [{"v": v, "qty": item["qty"]}]
    else:
        lines = [{"v": l["v"], "qty": l["qty"]} for l in Cart(request).lines()]
        if not lines:
            messages.warning(request, "Giỏ hàng đang trống.")
            return redirect("cart")
    profile = get_profile(request.user)
    data = request.POST if post else {}
    g = lambda k, d="": (data.get(k, d) if post else d)  # noqa: E731
    info = {
        "name": g("name", request.user.first_name),
        "phone": g("phone", profile.phone),
        "address": g("address", profile.default_address),
        "province_id": g("province_id"), "district_id": g("district_id"), "ward_code": g("ward_code"),
    }
    method = g("payment_method", OrderGroup.COD)
    global_code = g("global_code").strip()
    shop_codes = {}
    for ln in lines:
        sid = ln["v"].product.shop_id
        shop_codes[sid] = g(f"coupon_{sid}").strip()
    co = build_checkout(lines, global_code, shop_codes)
    shipping_error = ""
    shipping_quote = ""
    if settings.GHN_ENABLED:
        from django.core import signing
        from . import ghn
        try:
            ghn.quote_checkout(co, info, method)
            quote_state = {"total": co.total, "destination": [info["province_id"], info["district_id"], info["ward_code"]],
                           "parts": [[p.shop.pk, p.shipping, p.total] for p in co.parts]}
            shipping_quote = signing.dumps(quote_state, salt="ghn-quote")
        except OrderError as exc:
            shipping_error = str(exc)
            for part in co.parts:
                part.shipping = 0

    if post and data.get("action") == "place":
        try:
            if settings.GHN_ENABLED:
                if shipping_error:
                    raise OrderError(shipping_error)
                try:
                    accepted = signing.loads(data.get("shipping_quote", ""), salt="ghn-quote", max_age=900)
                except signing.BadSignature:
                    raise OrderError("Vui lòng bấm Tính phí GHN và kiểm tra tổng tiền trước khi đặt hàng.") from None
                if accepted != quote_state:
                    raise OrderError("Phí hoặc địa chỉ đã thay đổi. Vui lòng kiểm tra tổng tiền mới rồi đặt lại.")
                info["expected_total"] = co.total
            group = services.place_order(request.user, {l["v"].pk: l["qty"] for l in lines}, info, method, global_code, shop_codes,
                                         clear_cart=not is_buy_now)
            if is_buy_now:
                request.session.pop(BUY_NOW_KEY, None)
            if data.get("save_default"):
                _save_default_address(profile, info)
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
        "save_default": bool(post and data.get("save_default")),
        "buy_now": is_buy_now, "back_url": (item or {}).get("back") if is_buy_now else None,
        "provider_label": payments.provider_label(), "hold_minutes": getattr(settings, "PAYMENT_HOLD_MINUTES", 15),
        "ghn_enabled": settings.GHN_ENABLED, "shipping_error": shipping_error, "shipping_quote": shipping_quote,
    })


@customer_only
def order_success(request, group_id):
    payments.reconcile_user(request.user)
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
    if request.POST.get("from") == "reviews":
        return redirect("my_reviews")
    return redirect("order_detail", pk=pk)


# ----------------------------------------------------- thanh toán trực tuyến (UC07)
@customer_only
@require_POST
def pay_group(request, group_id):
    """Tạo yêu cầu thanh toán cho cả nhóm đơn rồi chuyển hướng sang VNPay/ZaloPay (hoặc cổng giả lập khi PAYMENT_PROVIDER=sandbox)."""
    try:
        txn = payments.create_payment(request.user, group_id)
        url = payments.start_online_payment(txn, request)
    except OrderError as e:
        messages.error(request, str(e))
        return redirect("order_success", group_id=group_id) if OrderGroup.objects.filter(pk=group_id, user=request.user).exists() \
            else redirect("my_orders")
    return redirect(url)


@customer_only
@require_GET
@never_cache
def payment_status(request, group_id):
    """Trang đặt hàng hỏi định kỳ (JS) để biết nhóm đơn đã thanh toán chưa, kể cả khi trang ZaloPay bị treo và không
    chuyển khách về. Mỗi lần hỏi sẽ đối soát với ZaloPay (/v2/query). state: paid | pending | failed | canceled."""
    group = get_object_or_404(OrderGroup, pk=group_id, user=request.user)
    if group.payment_method == OrderGroup.ONLINE:
        payments.reconcile_group(group.pk, throttle=10)
    live = [o for o in group.orders.all() if o.status != Order.CANCELED]
    if not live:
        state = "canceled"
    elif all(o.payment_status == Order.PAID for o in live):
        state = "paid"
        messages.success(request, "Thanh toán thành công. Người bán sẽ xác nhận đơn của bạn.")
    elif PaymentTransaction.objects.filter(group=group, status=PaymentTransaction.PENDING).exists():
        state = "pending"
    else:
        state = "failed"
    return JsonResponse({"state": state, "url": reverse("order_success", args=[group.pk])})


def sandbox_gateway(request, ref):
    """Cổng thanh toán GIẢ LẬP (Sandbox). Không nhận thông tin thẻ; chỉ cho chọn kết quả thử nghiệm."""
    txn = get_object_or_404(PaymentTransaction.objects.select_related("group"), ref=ref)
    if payments.provider() != "sandbox" or txn.provider != PaymentTransaction.SANDBOX or txn.group.user_id != request.user.pk:
        raise Http404   # cổng giả lập tự ký kết quả: không được mở khi dùng ZaloPay hay cho người khác
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


# -------------------------------------------------------------------- VNPay
@require_GET
def vnpay_ipn(request):
    """VNPay gọi vào đây (server-to-server) khi có kết quả. Không cần đăng nhập: xác thực nằm ở vnp_SecureHash (HMAC-SHA512).
    Luôn trả HTTP 200 kèm RspCode/Message theo đặc tả IPN của VNPay."""
    code, msg, _, _ = payments.process_vnpay(request.GET)
    return JsonResponse({"RspCode": code, "Message": msg})


@require_GET
def vnpay_return(request):
    """Khách được VNPay chuyển về sau khi thanh toán/hủy. Kết quả chỉ được tin khi chữ ký hợp lệ (xử lý chung với IPN)."""
    back = redirect("my_orders") if request.user.is_authenticated else redirect("home")
    code, _, outcome, txn = payments.process_vnpay(request.GET)
    if code == "97" or txn is None:
        messages.error(request, "Kết quả VNPay không hợp lệ hoặc không tìm thấy giao dịch, vui lòng xem trạng thái tại Đơn hàng của tôi.")
        return back
    if code == "04":
        messages.error(request, "Số tiền VNPay trả về không khớp giao dịch, kết quả bị từ chối.")
        return back
    if outcome == "BO_QUA" and txn.status == PaymentTransaction.SUCCESS:
        outcome = "THANH_CONG"                 # IPN đã xử lý trước khi khách quay về
    text = {
        "THANH_CONG": (messages.success, "Thanh toán VNPay thành công. Người bán sẽ xác nhận đơn của bạn."),
        "THAT_BAI": (messages.warning, "Thanh toán chưa thành công hoặc đã bị hủy tại VNPay. Bạn có thể thanh toán lại trong hạn giữ kho."),
        "BO_QUA": (messages.info, "Kết quả này đã được xử lý trước đó, đơn hàng không bị cập nhật lại."),
        "THANH_TOAN_MUON": (messages.warning, "Giao dịch đến muộn (đơn đã hủy hoặc đã thanh toán bằng giao dịch khác). "
                                              "Số tiền được chuyển sang Chờ hoàn tiền (mô phỏng)."),
    }[outcome]
    text[0](request, text[1])
    if request.user.is_authenticated and txn.group.user_id == request.user.pk:
        return redirect("order_success", group_id=txn.group_id)
    return back
