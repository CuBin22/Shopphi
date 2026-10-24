import re

<<<<<<< HEAD
from django.core.paginator import Paginator
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from . import services
from .models import BehaviorLog, Category, Product


<<<<<<< HEAD
PAGE_SIZE = 24


=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
def _int_or_none(value):
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else None


def home(request):
    actor = services.get_actor(request)
    products, personal = services.recommend(actor, limit=8)
<<<<<<< HEAD
    all_qs = services.search_queryset()
    banner_products = list(all_qs.exclude(image="").filter(stock__gt=0)[:5])
    return render(request, "catalog/home.html", {
        "banner_products": banner_products,
        "all_products": list(all_qs[:12]), "all_total": all_qs.count(),
=======
    return render(request, "catalog/home.html", {
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
        "recommended": products,
        "personal": personal,
        "trending": services.trending_keywords(),
    })


def search(request):
    actor = services.get_actor(request)
    q = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("danh_muc", "")
    price_from = _int_or_none(request.GET.get("gia_tu"))
    price_to = _int_or_none(request.GET.get("gia_den"))
    sort = request.GET.get("sap_xep", "moi")
    is_filter = request.GET.get("loc") == "1"          # đổi bộ lọc không tính là lần tìm mới
    if q and not is_filter:
        services.record_search(actor, q, from_suggestion=request.GET.get("goi_y") == "1")
<<<<<<< HEAD
    paginator = Paginator(services.search_queryset(q, category, price_from, price_to, sort), PAGE_SIZE)
    page = paginator.get_page(request.GET.get("trang"))      # trang sai/quá lớn tự về trang hợp lệ
    keep = request.GET.copy()
    keep.pop("trang", None)
    keep["loc"] = "1"                                         # đổi trang không tính là lần tìm mới
    return render(request, "catalog/search.html", {
        "q": q, "results": page.object_list, "page": page, "total": paginator.count,
        "page_query": keep.urlencode(), "category": category,
=======
    results = services.search_products(q, category, price_from, price_to, sort)
    return render(request, "catalog/search.html", {
        "q": q, "results": results, "category": category,
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
        "price_from": price_from or "", "price_to": price_to or "",
        "sort": sort, "sorts": [(k, v[0]) for k, v in services.SORTS.items()],
        "current_category": Category.objects.filter(slug=category).first(),
        "nguon": "tim-kiem" if q else "danh-muc",
    })


@require_GET
def suggest(request):
    items = services.suggest_keywords(request.GET.get("q", ""))
    return JsonResponse({"suggestions": items})


def product_detail(request, slug):
    actor = services.get_actor(request)
    qs = services.annotated(Product.objects.sellable())
    product = get_object_or_404(qs, slug=slug)
    if request.GET.get("nguon"):
        services.log_behavior(actor, BehaviorLog.CLICK, product, source=request.GET["nguon"][:30])
    services.log_behavior(actor, BehaviorLog.VIEW, product)
    recommended, personal = services.recommend(actor, current=product, limit=4)
    from shopping.models import Review
    reviews = Review.objects.filter(product=product).select_related("user").order_by("-created")
    agg = reviews.aggregate(avg=Avg("rating"), n=Count("id"))
<<<<<<< HEAD
    by_star = {r["rating"]: r["n"] for r in Review.objects.filter(product=product).values("rating").annotate(n=Count("id")).order_by()}
    rating_dist = [{"star": k, "n": by_star.get(k, 0), "pct": round(by_star.get(k, 0) * 100 / agg["n"]) if agg["n"] else 0} for k in (5, 4, 3, 2, 1)]
    return render(request, "catalog/product.html", {
        "p": product,
        "gallery": product.gallery(),
=======
    return render(request, "catalog/product.html", {
        "p": product,
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
        "variants": product.variants.all(),
        "recommended": recommended,
        "personal": personal,
        "reviews": reviews[:20],
        "rating_avg": round(agg["avg"], 1) if agg["avg"] else None,
        "rating_count": agg["n"],
<<<<<<< HEAD
        "rating_dist": rating_dist,
=======
>>>>>>> b5ec305f16c5d6ab95ed030332f7c84be485dcf5
    })
