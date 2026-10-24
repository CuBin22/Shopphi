from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def vnd(value):
    """1234567 -> 1.234.567 đ"""
    try:
        return f"{int(value):,}".replace(",", ".") + " đ"
    except (TypeError, ValueError):
        return ""


@register.filter
def tone(pk):
    """Chọn 1 trong 3 sắc độ cho ô ảnh minh họa, ổn định theo mã sản phẩm."""
    try:
        return int(pk) % 3
    except (TypeError, ValueError):
        return 0


@register.filter
def mul(a, b):
    try:
        return int(a) * int(b)
    except (TypeError, ValueError):
        return 0


@register.filter
def stars(n):
    try:
        n = int(round(float(n or 0)))
    except (TypeError, ValueError):
        n = 0
    return "★" * n + "☆" * (5 - n)


@register.simple_tag
def icon(name, cls=""):
    """Chèn icon từ bộ sprite trong catalog/_icons.html: {% icon "cart" %}."""
    return format_html('<svg class="i {}" aria-hidden="true" focusable="false"><use href="#i-{}"></use></svg>', cls, name)


@register.simple_tag
def rating_icons(value):
    """Năm ngôi sao: đầy theo điểm làm tròn, còn lại là sao rỗng."""
    try:
        n = max(0, min(5, int(round(float(value or 0)))))
    except (TypeError, ValueError):
        n = 0
    star = '<svg class="i star%s" aria-hidden="true" focusable="false"><use href="#i-star"></use></svg>'
    return mark_safe('<span class="rate" role="img" aria-label="%d trên 5 sao">%s</span>' % (
        n, "".join(star % ("" if k < n else " star--off") for k in range(5))))


@register.filter
def vnd_short(value):
    """Số tiền rút gọn cho trục biểu đồ: 1.250.000 -> 1,25tr; 500.000 -> 500k."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return ""
    if v >= 1_000_000_000:
        txt, unit = v / 1_000_000_000, "tỷ"
    elif v >= 1_000_000:
        txt, unit = v / 1_000_000, "tr"
    elif v >= 1_000:
        txt, unit = v / 1_000, "k"
    else:
        return str(v)
    return (("%.2f" % txt).rstrip("0").rstrip(".")).replace(".", ",") + unit


@register.filter
def date_end(point):
    """Nhãn ngày cuối của điểm biểu đồ cuối cùng (dd/mm)."""
    try:
        return point["end"].strftime("%d/%m")
    except (TypeError, KeyError, AttributeError):
        return ""


# ---- Nhãn tiếng Việt cho mã trạng thái (nhật ký đơn, giao dịch...) ----
_ORDER_STATUS = {"CHO_XAC_NHAN": "Chờ xác nhận", "DA_XAC_NHAN": "Đã xác nhận", "DANG_GIAO": "Đang giao",
                 "HOAN_THANH": "Hoàn thành", "DA_HUY": "Đã hủy"}
_PAY_STATUS = {"CHUA_THANH_TOAN": "Chưa thanh toán", "DA_THANH_TOAN": "Đã thanh toán",
               "CHO_HOAN_TIEN": "Chờ hoàn tiền", "DA_HOAN_TIEN": "Đã hoàn tiền"}
_TXN_STATUS = {"CHO_THANH_TOAN": "Chờ thanh toán", "THANH_CONG": "Thành công", "THAT_BAI": "Thất bại / hủy tại cổng",
               "HET_HAN": "Hết hạn giữ kho", "HET_HIEU_LUC": "Hết hiệu lực", "THANH_TOAN_MUON": "Thanh toán muộn"}
_CANCEL_RESULT = {"CHO_XU_LY": "Đang chờ Người bán xử lý", "CHAP_NHAN": "Đã chấp nhận", "TU_CHOI": "Bị từ chối"}


@register.filter
def order_status(code):
    """HOAN_THANH -> Hoàn thành (dùng cho nhật ký trạng thái)."""
    return _ORDER_STATUS.get(code, code or "")


@register.filter
def pay_status(code):
    return _PAY_STATUS.get(code, code or "")


@register.filter
def txn_status(code):
    return _TXN_STATUS.get(code, code or "")


@register.filter
def cancel_result(code):
    return _CANCEL_RESULT.get(code, code or "")


@register.filter
def actor_name(user):
    """Tên người thực hiện trong nhật ký; rỗng nghĩa là hệ thống tự động."""
    if user is None:
        return "Hệ thống"
    return user.first_name or user.get_username()
