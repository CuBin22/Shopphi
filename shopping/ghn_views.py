import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import ghn, shipping
from .models import Order
from .services import OrderError
from .views import customer_only


@customer_only
@require_GET
def addresses(request, kind):
    if not settings.GHN_ENABLED:
        return JsonResponse({"error": "GHN chưa bật."}, status=503)
    try:
        return JsonResponse({"data": ghn.addresses(kind, request.GET.get("parent", ""))})
    except OrderError as exc:
        return JsonResponse({"error": str(exc)}, status=400)


@csrf_exempt
@require_POST
def webhook(request):
    secret = settings.GHN_WEBHOOK_SECRET
    if not secret or not hmac.compare_digest(request.headers.get("X-GHN-Secret", ""), secret):
        return JsonResponse({"error": "Unauthorized"}, status=403)
    try:
        if len(request.body) > 65536:
            raise ValueError
        payload = json.loads(request.body)
        code = payload.get("OrderCode") if isinstance(payload, dict) else None
        if not isinstance(code, str) or not code or len(code) > 60:
            raise ValueError
    except (ValueError, UnicodeError):
        return JsonResponse({"error": "Invalid payload"}, status=400)
    order = Order.objects.filter(carrier="GHN", tracking_code=code).exclude(shipping_data={}).first()
    if not order:
        # Có thể callback đến trước khi giao dịch tạo đơn commit; yêu cầu GHN retry.
        return JsonResponse({"error": "Order not ready"}, status=503)
    try:
        shipping.sync_order(order.pk)
    except OrderError:
        return JsonResponse({"error": "GHN synchronization unavailable"}, status=503)
    return JsonResponse({"code": 200, "message": "Success"})
