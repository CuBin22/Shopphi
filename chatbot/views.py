import json

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from catalog.services import get_actor

from . import service


@require_POST
def chat(request):
    actor = get_actor(request)
    try:
        payload = json.loads(request.body.decode() or "{}")
    except ValueError:
        return JsonResponse({"error": "Dữ liệu không hợp lệ."}, status=400)
    pid = payload.get("product_id")
    try:
        pid = int(pid) if pid else None
    except (TypeError, ValueError):
        pid = None
    try:
        return JsonResponse(service.ask(actor, payload.get("message", ""), pid))
    except service.ChatError as e:
        return JsonResponse({"error": str(e)}, status=429 if "nhanh" in str(e) else 400)


@require_GET
def chat_history(request):
    return JsonResponse({"messages": service.history(get_actor(request))})
