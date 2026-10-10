"""Chatbot tư vấn (UC11): kiểm tra giới hạn -> chuẩn hóa/tách từ -> ý định -> truy xuất DB -> LLM -> ghi nhật ký."""
import json
import logging
import os
import re
import time
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from catalog.models import Product
from catalog.services import annotated
from catalog.text import khong_dau

from .models import ChatLog

logger = logging.getLogger(__name__)

MAX_LEN = 300
MAX_PER_MINUTE = 8
LLM_TIMEOUT = 15
STOP = set("la cua va cho toi minh ban co khong the nao a oi nhe nha duoc voi mot cai nay do thi sao gi".split())
INTENTS = {
    "PRICE": ["gia", "bao nhieu", "bao nhieu tien", "re", "dat"],
    "STOCK": ["con hang", "het hang", "ton kho", "con khong", "con bao nhieu", "mua duoc"],
    "SPEC": ["thong so", "pin", "cong suat", "dung luong", "ket noi", "kich thuoc", "chat lieu", "bao hanh", "tinh nang"],
    "RECOMMEND": ["goi y", "tu van", "nen mua", "tot nhat", "phu hop", "tim giup", "nen chon"],
}
SHOP_WORDS = {"mua", "san pham", "hang", "gia", "ship", "giao", "tai nghe", "sac", "loa", "chuot", "ban phim", "noi", "may",
              "den", "binh", "am", "do choi", "xep hinh", "robot", "gau", "bup be", "cap", "op lung", "dien thoai"}
GREET = ["xin chao", "chao", "hello", "hi "]


class ChatError(Exception):
    """Lỗi hiển thị cho người dùng (vượt giới hạn, tin nhắn rỗng...)."""


def mask_pii(text: str) -> str:
    """Che email, số điện thoại, số thẻ/tài khoản trước khi ghi nhật ký hoặc gửi LLM."""
    text = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", text)
    text = re.sub(r"(?<!\d)(?:\d[ .-]?){13,19}(?!\d)", "[số thẻ]", text)
    text = re.sub(r"(?<!\d)(\+?84|0)(?:[ .-]?\d){8,10}(?!\d)", "[số điện thoại]", text)
    return text


INTENT_WORDS = {w for ws in INTENTS.values() for phrase in ws for w in phrase.split()} | {"bao", "nhieu", "tien", "hang", "mua"}


def tokens(text: str):
    return [t for t in re.findall(r"[a-z0-9]+", khong_dau(text)) if t not in STOP and t not in INTENT_WORDS]


def detect_intent(plain: str) -> str:
    if any(plain.startswith(g.strip()) for g in GREET) and len(plain.split()) <= 3:
        return "GREETING"
    for name, words in INTENTS.items():
        if any(re.search(rf"\b{w}\b", plain) for w in words):
            return name
    return "GENERAL"


def retrieve(question: str, current_id=None, limit=3):
    """Sản phẩm đang hiển thị khớp câu hỏi. Giá, tồn kho, thông số lấy từ DB tại thời điểm trả lời."""
    qs = annotated(Product.objects.sellable()).prefetch_related("variants")
    found = []
    if current_id:
        cur = qs.filter(pk=current_id).first()
        if cur:
            found.append(cur)
    toks = set(tokens(question))
    if toks:
        scored = []
        for p in qs.exclude(pk__in=[f.pk for f in found]):
            hay = set(re.findall(r"[a-z0-9]+", khong_dau(f"{p.name} {p.brand} {p.tags}")))
            hits = len(toks & hay)
            if hits:
                scored.append((hits, p))
        scored.sort(key=lambda x: (-x[0], x[1].pk))
        found += [p for _, p in scored[: max(0, limit - len(found))]]
    return found[:limit]


def product_context(p) -> str:
    vs = "; ".join(f"{v.name}: {int(v.price):,}đ".replace(",", ".") + (f", còn {v.stock}" if v.stock else ", hết hàng")
                   for v in p.variants.all())
    specs = "; ".join(f"{k}: {v}" for k, v in p.spec_rows())
    return (f"- {p.name} (gian hàng {p.shop.name}, danh mục {p.category.name}, thương hiệu {p.brand or 'không rõ'}). "
            f"Biến thể/giá/tồn kho: {vs}. Thông số: {specs or 'chưa có'}. Mô tả: {p.description[:200]}")


def _offline_answer(intent, products):
    """Chế độ không có khóa API LLM: soạn câu trả lời trực tiếp từ dữ liệu sản phẩm."""
    lines = []
    for p in products:
        vs = ", ".join(f"{v.name} {int(v.price):,}đ".replace(",", ".") + (f" (còn {v.stock})" if v.stock else " (hết hàng)")
                       for v in p.variants.all())
        if intent == "SPEC":
            specs = "; ".join(f"{k}: {v}" for k, v in p.spec_rows()) or "chưa có thông số chi tiết"
            lines.append(f"{p.name} ({p.shop.name}): {specs}.")
        elif intent == "STOCK":
            lines.append(f"{p.name} ({p.shop.name}): {vs}.")
        else:
            lines.append(f"{p.name} ({p.shop.name}): {vs}. {p.description[:120]}")
    head = "Mình tìm được các sản phẩm phù hợp:\n" if len(products) > 1 else ""
    return head + "\n".join(lines)


def call_llm(question: str, contexts: list, intent: str) -> str:
    """Gọi API Anthropic (Messages). Khóa API đọc từ biến môi trường, không đặt trong mã front-end (NFR04)."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    system = ("Bạn là trợ lý tư vấn mua sắm của sàn Shopphi. Chỉ trả lời bằng tiếng Việt, ngắn gọn, "
              "và CHỈ dựa vào dữ liệu sản phẩm được cung cấp (giá, tồn kho, thông số). Không bịa thông tin. "
              "Nếu thiếu dữ liệu, hãy nói chưa có thông tin và gợi ý liên hệ gian hàng. Không trả lời ngoài phạm vi mua sắm.")
    body = {"model": getattr(settings, "CHATBOT_MODEL", "claude-sonnet-5-5"), "max_tokens": 500, "system": system,
            "messages": [{"role": "user", "content": f"Dữ liệu sản phẩm:\n" + "\n".join(contexts) + f"\n\nCâu hỏi: {question}"}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
        data = json.loads(r.read().decode())
    return "".join(b.get("text", "") for b in data.get("content", [])).strip()


def ask(actor, message: str, current_product_id=None):
    """Trả về dict {answer, status}. Mọi lượt hỏi (kể cả bị từ chối) đều được ghi vào ChatLog."""
    message = (message or "").strip()
    if not message:
        raise ChatError("Hãy nhập câu hỏi.")
    if len(message) > MAX_LEN:
        raise ChatError(f"Câu hỏi quá dài, tối đa {MAX_LEN} ký tự.")
    recent = ChatLog.objects.filter(created__gte=timezone.now() - timedelta(minutes=1))
    recent = recent.filter(user=actor.user) if actor.user else recent.filter(session_key=actor.session_key)
    if recent.count() >= MAX_PER_MINUTE:
        raise ChatError("Bạn gửi tin nhắn quá nhanh, vui lòng thử lại sau ít phút.")

    started = time.monotonic()
    masked = mask_pii(message)
    plain = khong_dau(masked)
    intent = detect_intent(plain)
    status, provider, products = ChatLog.OK, "", []

    if intent == "GREETING":
        answer = "Xin chào! Mình có thể giúp bạn xem giá, tồn kho, thông số hoặc gợi ý sản phẩm. Bạn đang cần món gì?"
    else:
        products = retrieve(masked, current_product_id)
        in_scope = bool(products) or intent != "GENERAL" or any(w in plain for w in SHOP_WORDS)
        if not in_scope:
            status = ChatLog.REFUSED
            answer = "Xin lỗi, mình chỉ tư vấn trong phạm vi mua sắm trên Shopphi (giá, tồn kho, thông số, gợi ý sản phẩm)."
        elif not products:
            status = ChatLog.REFUSED
            answer = ("Mình chưa tìm thấy sản phẩm phù hợp để trả lời chính xác. "
                      "Bạn thử nêu rõ tên sản phẩm hơn, hoặc liên hệ trực tiếp gian hàng để được hỗ trợ.")
        else:
            contexts = [product_context(p) for p in products]
            if os.environ.get("ANTHROPIC_API_KEY"):
                provider = "anthropic"
                try:
                    answer = call_llm(masked, contexts, intent) or _offline_answer(intent, products)
                except Exception:  # noqa: BLE001  (lỗi mạng, hết hạn chờ, khóa sai...)
                    logger.warning("Lỗi gọi LLM", exc_info=True)
                    status = ChatLog.ERROR
                    answer = "Hiện chatbot tạm thời chưa tư vấn được. Bạn vui lòng thử lại sau hoặc liên hệ gian hàng."
            else:
                provider = "offline"
                answer = _offline_answer(intent, products)

    try:
        ChatLog.objects.create(
            user=actor.user, session_key=actor.session_key, question=masked[:500], answer=answer, intent=intent,
            product_ids=",".join(str(p.pk) for p in products), status=status, provider=provider,
            latency_ms=int((time.monotonic() - started) * 1000))
    except Exception:  # noqa: BLE001
        logger.warning("Không ghi được nhật ký chatbot", exc_info=True)
    return {"answer": answer, "status": status}


def history(actor, limit=30):
    q = ChatLog.objects.filter(user=actor.user) if actor.user else ChatLog.objects.filter(session_key=actor.session_key)
    rows = list(q.order_by("-created", "-id")[:limit])[::-1]
    return [{"q": r.question, "a": r.answer} for r in rows]
