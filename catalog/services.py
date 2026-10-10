"""Nghiệp vụ: ghi log hành vi, tìm kiếm, gợi ý từ khóa, gợi ý sản phẩm."""
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import F, Min, Q, Sum

from .models import BehaviorLog, Keyword, Product
from .text import chuan_hoa, khong_dau, tu_khoa_hop_le

logger = logging.getLogger(__name__)

# ---- Tham số (các điểm "Open Issues" trong đặc tả được chốt tạm ở đây) ----
SUGGEST_LIMIT = 8            # tối đa 8 gợi ý cùng lúc
SUGGEST_MIN_FREQ = 3         # chỉ gợi ý từ khóa có tần suất >= 3
FUZZY_MIN = 0.6              # độ tương đồng chuỗi tối thiểu (difflib)
WEIGHTS = {BehaviorLog.VIEW: 1, BehaviorLog.CLICK: 2, BehaviorLog.ADD: 3, BehaviorLog.PURCHASE: 5}
WEIGHT_CAP = 10              # trần điểm quan tâm cho mỗi (người dùng, sản phẩm)
MIN_PRODUCTS_FOR_PERSONAL = 3  # ít hơn số sản phẩm đã tương tác này => dùng gợi ý dự phòng


@dataclass
class Actor:
    """Người dùng đang đăng nhập hoặc phiên ẩn danh."""
    session_key: str
    user: object = None


def get_actor(request) -> Actor:
    if not request.session.session_key:
        request.session.create()
    user = request.user if request.user.is_authenticated else None
    return Actor(session_key=request.session.session_key, user=user)


# ---------------------------------------------------------------- log hành vi
def log_behavior(actor: Actor, type_, product=None, keyword="", source=""):
    """Ghi log ngầm; lỗi ghi log không làm gián đoạn người dùng (NV9)."""
    try:
        BehaviorLog.objects.create(
            user=actor.user, session_key=actor.session_key, product=product,
            type=type_, keyword=keyword[:120], source=source[:30],
        )
    except Exception:  # noqa: BLE001
        logger.warning("Không ghi được log hành vi", exc_info=True)


def count_matches(plain_phrase: str) -> int:
    qs = Product.objects.sellable()
    for token in plain_phrase.split():
        qs = qs.filter(search_text__contains=token)
    return qs.count()


def refresh_keyword_counts():
    changed = []
    for kw in Keyword.objects.all():
        n = count_matches(kw.plain)
        if n != kw.match_count:
            kw.match_count = n
            changed.append(kw)
    if changed:
        Keyword.objects.bulk_update(changed, ["match_count"])


def record_search(actor: Actor, text: str, from_suggestion=False):
    """Ghi hành vi Search và cập nhật tần suất từ khóa trong từ điển."""
    q = chuan_hoa(text)
    if not q:
        return
    log_behavior(actor, BehaviorLog.SEARCH, keyword=q, source="GOI_Y" if from_suggestion else "TIM_KIEM")
    if not tu_khoa_hop_le(q):
        return
    try:
        plain = khong_dau(q)
        kw, created = Keyword.objects.get_or_create(plain=plain, defaults={"phrase": q})
        Keyword.objects.filter(pk=kw.pk).update(frequency=F("frequency") + 1)
        if created:
            kw.match_count = count_matches(plain)
            kw.save(update_fields=["match_count"])
    except Exception:  # noqa: BLE001
        logger.warning("Không cập nhật được từ điển từ khóa", exc_info=True)


# ------------------------------------------------------------- gợi ý từ khóa
def suggest_keywords(raw: str, limit=SUGGEST_LIMIT):
    """Gợi ý tức thời: tiền tố / đầu từ / độ tương đồng chuỗi, xếp theo tần suất.

    Chỉ gợi ý từ khóa đang hiện, có sản phẩm đang hiển thị và tần suất đủ lớn.
    """
    plain = khong_dau(raw)
    if not plain:
        return []
    candidates = Keyword.objects.filter(
        visible=True, match_count__gt=0, frequency__gte=SUGGEST_MIN_FREQ
    ).order_by("-frequency")[:2000]
    found = []
    for kw in candidates:
        if kw.plain.startswith(plain):
            rank = 0
        elif any(w.startswith(plain) for w in kw.plain.split()):
            rank = 1
        elif len(plain) >= 3 and SequenceMatcher(None, plain, kw.plain[: len(plain) + 2]).ratio() >= FUZZY_MIN:
            rank = 2
        else:
            continue
        found.append((rank, -kw.frequency, kw.phrase))
    found.sort()
    return [p for _, _, p in found[: min(limit, SUGGEST_LIMIT)]]


# ------------------------------------------------------------------ tìm kiếm
SORTS = {
    "moi": ("Mới nhất", ("-created", "-id")),
    "gia-tang": ("Giá thấp đến cao", ("price", "id")),
    "gia-giam": ("Giá cao đến thấp", ("-price", "id")),
}


def annotated(qs):
    return qs.select_related("shop", "category").annotate(price=Min("variants__price"), stock=Sum("variants__stock"))


def search_products(q="", category="", price_from=None, price_to=None, sort="moi", limit=60):
    qs = annotated(Product.objects.sellable())
    for token in khong_dau(q).split():
        qs = qs.filter(search_text__contains=token)
    if category:
        qs = qs.filter(category__slug=category)
    if price_from is not None:
        qs = qs.filter(price__gte=price_from)
    if price_to is not None:
        qs = qs.filter(price__lte=price_to)
    order = SORTS.get(sort, SORTS["moi"])[1]
    return list(qs.order_by(*order)[:limit])


# ------------------------------------------------------------ gợi ý sản phẩm
def _build_index():
    rows = (
        BehaviorLog.objects.filter(product__isnull=False, type__in=list(WEIGHTS))
        .order_by("-id")
        .values_list("user_id", "session_key", "product_id", "type")[:30000]
    )
    vec = defaultdict(lambda: defaultdict(float))
    for uid, sk, pid, t in rows:
        vec[f"u{uid}" if uid else f"s{sk}"][pid] += WEIGHTS[t]
    vec = {k: {p: min(w, WEIGHT_CAP) for p, w in d.items()} for k, d in vec.items()}
    norm, inv = defaultdict(float), defaultdict(list)
    for key, d in vec.items():
        for p, w in d.items():
            norm[p] += w * w
            inv[p].append(key)
    return vec, {p: math.sqrt(v) for p, v in norm.items()}, dict(inv)


def _index():
    return cache.get_or_set("rec_index", _build_index, 60)


def _profile(actor: Actor):
    q = Q(session_key=actor.session_key)
    if actor.user:
        q |= Q(user=actor.user)
    prof = defaultdict(float)
    rows = BehaviorLog.objects.filter(q, product__isnull=False, type__in=list(WEIGHTS)).values_list("product_id", "type")
    for pid, t in rows:
        prof[pid] += WEIGHTS[t]
    return {p: min(w, WEIGHT_CAP) for p, w in prof.items()}


def _item_scores(seeds, skip_keys):
    """Độ phù hợp theo cosine giữa các sản phẩm, dựa trên hành vi của những người dùng khác."""
    vec, norm, inv = _index()
    score = defaultdict(float)
    for s, ws in seeds.items():
        for key in inv.get(s, ()):
            if key in skip_keys:
                continue
            d = vec[key]
            a = d[s]
            for p, w in d.items():
                if p == s or p in seeds:
                    continue
                score[p] += ws * a * w / (norm[s] * norm[p])
    return score


def _popular_rank():
    def build():
        score = defaultdict(float)
        rows = BehaviorLog.objects.filter(product__isnull=False, type__in=list(WEIGHTS)).values_list("product_id", "type")
        for pid, t in rows:
            score[pid] += WEIGHTS[t]
        ordered = sorted(score, key=lambda p: -score[p])
        return {p: i for i, p in enumerate(ordered)}
    return cache.get_or_set("rec_popular", build, 60)


def _in_stock(extra=None):
    qs = annotated(Product.objects.sellable()).filter(stock__gt=0)
    return qs.filter(extra) if extra is not None else qs


def _fallback(limit, exclude, category=None):
    """Dự phòng: sản phẩm phổ biến (trang chủ) hoặc cùng danh mục (trang chi tiết)."""
    qs = _in_stock().exclude(pk__in=exclude)
    if category is not None:
        qs = qs.filter(category=category)
    rank = _popular_rank()
    return sorted(qs, key=lambda p: (rank.get(p.pk, 10**9), -p.pk))[:limit]


def recommend(actor: Actor, current=None, limit=8):
    """Trả về (danh sách sản phẩm, có_cá_nhân_hóa).

    Người dùng mới hoặc chưa đủ dữ liệu dùng cơ chế dự phòng; thiếu sau khi lọc thì bổ sung dự phòng.
    """
    profile = _profile(actor)
    exclude = set([current.pk]) if current else set()
    products = []
    if len(profile) >= MIN_PRODUCTS_FOR_PERSONAL:
        seeds = dict(profile)
        if current:
            seeds[current.pk] = seeds.get(current.pk, 0) + 4
        skip = {f"s{actor.session_key}"} | ({f"u{actor.user.pk}"} if actor.user else set())
        scores = _item_scores(seeds, skip)
        ids = [p for p in sorted(scores, key=lambda p: -scores[p]) if p not in exclude and p not in profile]
        by_id = {p.pk: p for p in _in_stock(Q(pk__in=ids[: limit * 3]))}
        products = [by_id[i] for i in ids if i in by_id][:limit]
    personal = bool(products)
    if len(products) < limit:
        taken = exclude | {p.pk for p in products}
        cat = current.category if current else None
        products += _fallback(limit - len(products), taken, category=cat)
        if len(products) < limit and cat is not None:
            taken = exclude | {p.pk for p in products}
            products += _fallback(limit - len(products), taken)
    return products, personal


def trending_keywords(limit=8):
    return list(
        Keyword.objects.filter(visible=True, match_count__gt=0, frequency__gte=SUGGEST_MIN_FREQ)
        .order_by("-frequency").values_list("phrase", flat=True)[:limit]
    )
