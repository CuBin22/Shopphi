"""Thống kê và báo cáo (UC19). Doanh thu = tổng (tạm tính - giảm giá) của đơn Hoàn thành, không gồm phí vận chuyển."""
import math
from datetime import date, timedelta

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from catalog.models import Keyword, Shop, Variant

from .models import Order, OrderStatusLog


class ReportError(Exception):
    pass


def validate_period(d_from: date, d_to: date):
    if d_to > timezone.localdate():
        raise ReportError("Kỳ báo cáo không được chứa ngày trong tương lai.")
    if d_from > d_to:
        raise ReportError("Từ ngày phải nhỏ hơn hoặc bằng đến ngày.")


def stats(d_from: date, d_to: date, shops):
    """Trả về danh sách dòng thống kê theo gian hàng cho kỳ [d_from, d_to]."""
    validate_period(d_from, d_to)
    rows = []
    for shop in shops:
        done = Order.objects.filter(shop=shop, status=Order.DONE, status_logs__new_status=Order.DONE,
                                    status_logs__at__date__gte=d_from, status_logs__at__date__lte=d_to)
        agg = done.aggregate(n=Count("pk", distinct=True), sub=Sum("subtotal"), disc_s=Sum("shop_discount"),
                             disc_g=Sum("global_discount"))
        revenue = (agg["sub"] or 0) - (agg["disc_s"] or 0) - (agg["disc_g"] or 0)
        canceled = OrderStatusLog.objects.filter(order__shop=shop, order__status=Order.CANCELED,
                                                 new_status=Order.CANCELED, at__date__gte=d_from, at__date__lte=d_to)
        stock = Variant.objects.filter(product__shop=shop).aggregate(s=Sum("stock"))["s"] or 0
        rows.append({
            "shop": shop, "done": agg["n"], "revenue": revenue,
            "cancel_manual": canceled.filter(actor__isnull=False).count(),
            "cancel_auto": canceled.filter(actor__isnull=True).count(),
            "stock": stock,
        })
    return rows


def popular_keywords(limit=10):
    """Số liệu tổng hợp ẩn danh (chỉ Quản trị viên xem)."""
    return list(Keyword.objects.filter(frequency__gt=0).order_by("-frequency")[:limit])


def daily_revenue(d_from: date, d_to: date, shop=None):
    """Doanh thu và số đơn hoàn thành theo từng ngày (giờ Việt Nam) trong kỳ; ngày không có đơn trả về 0."""
    validate_period(d_from, d_to)
    qs = OrderStatusLog.objects.filter(new_status=Order.DONE, order__status=Order.DONE,
                                       at__date__gte=d_from, at__date__lte=d_to)
    if shop is not None:
        qs = qs.filter(order__shop=shop)
    rows = qs.annotate(d=TruncDate("at")).values("d").annotate(
        rev=Sum(F("order__subtotal") - F("order__shop_discount") - F("order__global_discount")),
        n=Count("order", distinct=True))
    by_day = {r["d"]: r for r in rows}
    out, d = [], d_from
    while d <= d_to:
        r = by_day.get(d)
        out.append({"start": d, "end": d, "revenue": int(r["rev"] or 0) if r else 0, "done": r["n"] if r else 0})
        d += timedelta(days=1)
    return out


def _nice_ceiling(v):
    if v <= 0:
        return 0
    base = 10 ** int(math.floor(math.log10(v)))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * base:
            return int(m * base)
    return int(10 * base)


def chart_data(series, max_columns=45):
    """Gộp ngày thành nhóm khi kỳ quá dài (để cột không quá mảnh), tính chiều cao cột theo % của mốc tròn."""
    size = max(1, math.ceil(len(series) / max_columns))
    points = []
    for i in range(0, len(series), size):
        chunk = series[i:i + size]
        points.append({"start": chunk[0]["start"], "end": chunk[-1]["end"],
                       "revenue": sum(c["revenue"] for c in chunk), "done": sum(c["done"] for c in chunk)})
    top = _nice_ceiling(max((p["revenue"] for p in points), default=0))
    for p in points:
        p["h"] = round(p["revenue"] * 100 / top, 2) if top else 0
    return {"points": points, "top": top, "mid": top // 2, "bucket_days": size,
            "total": sum(p["revenue"] for p in points), "done": sum(p["done"] for p in points)}
