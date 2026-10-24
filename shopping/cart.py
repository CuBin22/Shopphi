"""Giỏ hàng. Khách đã đăng nhập: lưu bảng CartItem (PostgreSQL). Khách vãng lai: lưu trong session,
được gộp vào giỏ trong cơ sở dữ liệu khi đăng nhập."""
from django.contrib import messages

from catalog.models import Product, Shop, Variant

from .models import CartItem


def _is_customer(user):
    from accounts.utils import get_role
    from accounts.models import Profile
    return user.is_authenticated and get_role(user) == Profile.CUSTOMER


class Cart:
    def __init__(self, request):
        self.request = request
        self.db = _is_customer(request.user)

    # ---- đọc/ghi thô: {variant_id: qty}
    def raw(self):
        if self.db:
            return dict(CartItem.objects.filter(user=self.request.user).values_list("variant_id", "qty"))
        return {int(k): int(v) for k, v in self.request.session.get("cart", {}).items()}

    def _save_session(self, data):
        self.request.session["cart"] = {str(k): v for k, v in data.items()}

    def quantity_of(self, variant_id):
        return self.raw().get(int(variant_id), 0)

    def count(self):
        return sum(self.raw().values())

    def set(self, variant_id, qty):
        variant_id = int(variant_id)
        if self.db:
            CartItem.objects.update_or_create(user=self.request.user, variant_id=variant_id, defaults={"qty": qty})
        else:
            data = self.raw()
            data[variant_id] = qty
            self._save_session(data)

    def remove(self, variant_ids):
        ids = [int(i) for i in (variant_ids if isinstance(variant_ids, (list, set, tuple)) else [variant_ids])]
        if self.db:
            CartItem.objects.filter(user=self.request.user, variant_id__in=ids).delete()
        else:
            data = self.raw()
            for i in ids:
                data.pop(i, None)
            self._save_session(data)

    def lines(self, notify=True):
        """Các dòng hợp lệ; tự loại sản phẩm ngừng bán hoặc thuộc gian hàng bị khóa (QĐ8)."""
        raw = self.raw()
        variants = Variant.objects.filter(
            pk__in=raw.keys(), product__status=Product.VISIBLE, product__shop__status=Shop.ACTIVE
        ).select_related("product__shop", "product__category")
        found = {v.pk: v for v in variants}
        lines, dropped = [], []
        for vid, qty in raw.items():
            v = found.get(vid)
            if v is None:
                dropped.append(vid)
                continue
            lines.append({"v": v, "qty": qty, "total": v.price * qty, "over": qty > v.stock})
        if dropped:
            self.remove(dropped)
            if notify:
                messages.warning(self.request, "Một sản phẩm đã ngừng bán nên được loại khỏi giỏ hàng.")
        lines.sort(key=lambda l: (l["v"].product.shop_id, l["v"].pk))
        return lines

    def grouped(self):
        """[{shop, lines, subtotal}] gom theo gian hàng."""
        groups = {}
        for line in self.lines():
            groups.setdefault(line["v"].product.shop, []).append(line)
        return [{"shop": s, "lines": ls, "subtotal": sum(l["total"] for l in ls)} for s, ls in groups.items()]


def merge_session_cart(request, user):
    """Gộp giỏ trong session (lúc chưa đăng nhập) vào giỏ của tài khoản, không vượt tồn kho."""
    data = request.session.pop("cart", None)
    if not data:
        return
    stock = {v.pk: v.stock for v in Variant.objects.filter(pk__in=[int(k) for k in data])}
    for k, qty in data.items():
        vid = int(k)
        if vid not in stock or stock[vid] <= 0:
            continue
        item, created = CartItem.objects.get_or_create(user=user, variant_id=vid, defaults={"qty": 1})
        item.qty = min(stock[vid], (0 if created else item.qty) + int(qty))
        item.save(update_fields=["qty"])
