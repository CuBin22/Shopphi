from django import template

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
