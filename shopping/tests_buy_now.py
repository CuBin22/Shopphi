"""Kiểm thử "Mua ngay" ở trang chi tiết sản phẩm và lỗi trang chi tiết đơn của Người bán (nhật ký do hệ thống ghi)."""
from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from shopping import services
from shopping.models import CartItem, Order, OrderGroup

from .tests import Base

INFO = {"name": "An", "phone": "0900000000", "address": "12 Lê Lợi, HCM"}


class BuyNowTests(Base):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.login(username="khach", password="abc12345")

    def start(self, variant=None, qty=1):
        return self.c.post(reverse("buy_now"), {"variant": (variant or self.a).pk, "qty": qty})

    def test_product_page_has_buy_now_button(self):
        r = self.c.get(self.p1.get_absolute_url())
        self.assertContains(r, 'id="buynow"')
        self.assertContains(r, reverse("buy_now"))

    def test_buy_now_goes_to_checkout_with_only_that_item_and_keeps_cart(self):
        r = self.start(self.b, 2)
        self.assertRedirects(r, reverse("checkout") + "?mua-ngay=1")
        page = self.c.get(reverse("checkout") + "?mua-ngay=1")
        self.assertContains(page, "Sạc B")
        self.assertNotContains(page, "Tai nghe A")                 # sản phẩm trong giỏ không bị kéo vào
        self.assertContains(page, 'name="mua_ngay"')
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 2)   # giỏ giữ nguyên

    def test_place_buy_now_creates_single_order_and_keeps_cart(self):
        self.start(self.b, 2)
        stock = self.b.stock
        r = self.c.post(reverse("checkout"), {**INFO, "mua_ngay": "1", "payment_method": "COD", "action": "place"})
        g = OrderGroup.objects.get(user=self.cust)
        self.assertRedirects(r, reverse("order_success", args=[g.pk]))
        self.assertEqual(g.orders.count(), 1)
        o = g.orders.get()
        self.assertEqual(o.items.get().qty, 2)
        self.assertEqual(o.subtotal, 400000)
        self.assertEqual(o.total, 400000 + services.SHIPPING_FEE)
        self.b.refresh_from_db()
        self.assertEqual(self.b.stock, stock - 2)
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 2)   # mua ngay không xóa giỏ
        self.assertNotIn("buy_now", self.c.session)                            # phiên mua ngay đã dùng xong

    def test_coupon_applies_in_buy_now(self):
        self.start(self.a, 1)
        page = self.c.post(reverse("checkout"), {**INFO, "mua_ngay": "1", "payment_method": "COD", "action": "apply",
                                                 "global_code": "TOANSAN"})
        self.assertContains(page, "Đã áp mã TOANSAN")
        self.assertContains(page, 'name="mua_ngay"')

    def test_cart_checkout_still_works_and_clears_cart(self):
        r = self.c.post(reverse("checkout"), {**INFO, "payment_method": "COD", "action": "place"})
        g = OrderGroup.objects.get(user=self.cust)
        self.assertEqual(g.orders.count(), 2)
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 0)

    def test_rejects_over_stock_and_out_of_stock(self):
        r = self.start(self.b, self.b.stock + 1)
        self.assertRedirects(r, self.p2.get_absolute_url())
        self.assertNotIn("buy_now", self.c.session)
        self.b.stock = 0
        self.b.save()
        r = self.start(self.b, 1)
        self.assertRedirects(r, self.p2.get_absolute_url())

    def test_stock_dropping_after_click_is_caught_at_checkout(self):
        self.start(self.b, 3)
        self.b.stock = 1
        self.b.save()
        r = self.c.get(reverse("checkout") + "?mua-ngay=1")
        self.assertRedirects(r, self.p2.get_absolute_url())

    def test_hidden_product_cannot_be_bought_now(self):
        self.p2.status = "AN"
        self.p2.save()
        r = self.start(self.b, 1)
        self.assertRedirects(r, self.p2.get_absolute_url(), fetch_redirect_response=False)
        self.assertNotIn("buy_now", self.c.session)

    def test_anonymous_is_sent_to_login(self):
        r = Client().post(reverse("buy_now"), {"variant": self.a.pk, "qty": 1})
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r["Location"])

    def test_vendor_cannot_buy_now(self):
        v = Client()
        v.login(username="ban1", password="abc12345")
        r = v.post(reverse("buy_now"), {"variant": self.b.pk, "qty": 1})
        self.assertRedirects(r, self.p2.get_absolute_url())
        self.assertNotIn("buy_now", v.session)

    def test_checkout_buy_now_without_session_goes_back_to_cart(self):
        r = self.c.get(reverse("checkout") + "?mua-ngay=1")
        self.assertRedirects(r, reverse("cart"))

    def test_buy_now_requires_post(self):
        self.assertEqual(self.c.get(reverse("buy_now")).status_code, 405)

    def test_online_payment_buy_now_sets_hold(self):
        self.start(self.a, 1)
        self.c.post(reverse("checkout"), {**INFO, "mua_ngay": "1", "payment_method": "CONG_THANH_TOAN", "action": "place"})
        g = OrderGroup.objects.get(user=self.cust)
        self.assertIsNotNone(g.hold_until)


class VendorOrderDetailSystemLogTests(Base):
    """Trước đây trang chi tiết đơn của Người bán bị lỗi khi nhật ký có dòng do hệ thống tự ghi (actor rỗng)."""

    def test_vendor_detail_renders_with_system_actor_logs(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "SYS-1")
        # hệ thống tự hoàn thành sau 7 ngày
        Order.objects.filter(pk=o.pk).update(shipped_at=timezone.now() - timedelta(days=8))
        services.complete_order(o.pk, actor=None, auto=True)
        c = Client()
        c.login(username="ban1", password="abc12345")
        r = c.get(reverse("vendor_order_detail", args=[o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Hệ thống")
        self.assertContains(r, "Hoàn thành")
        html = r.content.decode()
        tl = html[html.index('class="timeline"'):]
        tl = tl[:tl.index("</ul>")]
        for raw in ("CHO_XAC_NHAN", "DA_XAC_NHAN", "DANG_GIAO", "HOAN_THANH"):
            self.assertNotIn(raw, tl)

    def test_vendor_detail_after_auto_cancel(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        services.cancel_order(o.pk, None, "Hết hạn thanh toán", auto=True)
        c = Client()
        c.login(username="ban1", password="abc12345")
        r = c.get(reverse("vendor_order_detail", args=[o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Hệ thống")
