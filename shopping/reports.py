"""Thống kê và báo cáo (UC19). Doanh thu = tổng (tạm tính - giảm giá) của đơn Hoàn thành, không gồm phí vận chuyển."""
from datetime import date

from django.db.models import Count, Q, Sum
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
