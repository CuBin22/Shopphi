from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from catalog.models import Category, Product, Shop, Variant
from chatbot.models import ChatLog
from shopping import reports, services
from shopping.models import CartItem, Coupon, Order, Review
from shopping.services import OrderError

User = get_user_model()


def mk_user(name, role):
    u = User.objects.create_user(name, password="abc12345", first_name=name)
    Profile.objects.create(user=u, role=role)
    return u


class Base(TestCase):
    def setUp(self):
        self.cat = Category.objects.create(slug="do-cong-nghe", name="Đồ công nghệ")
        self.v1u, self.v2u = mk_user("ban1", Profile.VENDOR), mk_user("ban2", Profile.VENDOR)
        self.s1 = Shop.objects.create(name="S1", status=Shop.ACTIVE, owner=self.v1u)
        self.s2 = Shop.objects.create(name="S2", status=Shop.ACTIVE, owner=self.v2u)
        self.p1 = Product.objects.create(shop=self.s1, category=self.cat, name="Tai nghe A", tags="tai nghe", description="x")
        self.p2 = Product.objects.create(shop=self.s2, category=self.cat, name="Sạc B", tags="sạc", description="y")
        self.a = Variant.objects.create(product=self.p1, name="Đen", price=300000, stock=10)
        self.b = Variant.objects.create(product=self.p2, name="Trắng", price=200000, stock=5)
        self.cust = mk_user("khach", Profile.CUSTOMER)
        self.admin = mk_user("adm", Profile.ADMIN)
        now = timezone.now()
        self.gc = Coupon.objects.create(code="TOANSAN", scope="TOAN_SAN", kind="PHAN_TRAM", value=10, max_discount=40000,
                                        min_order=100000, starts=now - timedelta(days=1), expires=now + timedelta(days=1), max_uses=2)
        self.sc = Coupon.objects.create(code="SHOP1", scope="GIAN_HANG", shop=self.s1, kind="SO_TIEN", value=20000,
                                        starts=now - timedelta(days=1), expires=now + timedelta(days=1), max_uses=5)
        CartItem.objects.create(user=self.cust, variant=self.a, qty=2)
        CartItem.objects.create(user=self.cust, variant=self.b, qty=1)

    def order(self, **kw):
        return services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1},
                                    {"name": "A", "phone": "0900000000", "address": "HCM"}, "COD", **kw)


class AccountTests(TestCase):
    def test_register_login_lockout_and_session_merge(self):
        c = Client()
        r = c.post(reverse("register"), {"full_name": "An", "identifier": "an@x.vn", "role": "KHACH_HANG", "password": "abc12345",
                                         "password2": "abc12345", "agree": "on"})
        self.assertRedirects(r, reverse("login"))
        self.assertTrue(User.objects.filter(username="an@x.vn").exists())
        r = c.post(reverse("register"), {"full_name": "An", "identifier": "AN@x.vn", "role": "KHACH_HANG", "password": "abc12345",
                                         "password2": "abc12345", "agree": "on"})
        self.assertContains(r, "đã có tài khoản")
        r = c.post(reverse("register"), {"full_name": "B", "identifier": "b@x.vn", "role": "KHACH_HANG", "password": "abcdefgh",
                                         "password2": "abcdefgh", "agree": "on"})
        self.assertContains(r, "gồm cả chữ và số")
        for _ in range(5):
            r = c.post(reverse("login"), {"identifier": "an@x.vn", "password": "sai"})
        self.assertContains(r, "tạm khóa")
        r = c.post(reverse("login"), {"identifier": "an@x.vn", "password": "abc12345"})
        self.assertContains(r, "tạm khóa")                # đúng mật khẩu vẫn bị khóa
        p = Profile.objects.get(user__username="an@x.vn")
        p.locked_until = timezone.now() - timedelta(minutes=1)
        p.save()
        # hành vi ẩn danh được gắn vào tài khoản sau khi đăng nhập
        c2 = Client()
        c2.get("/")
        from catalog.models import BehaviorLog
        BehaviorLog.objects.create(session_key=c2.session.session_key, type="VIEW")
        r = c2.post(reverse("login"), {"identifier": "an@x.vn", "password": "abc12345"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(BehaviorLog.objects.filter(user__username="an@x.vn").count(), 1)

    def test_anonymous_cart_merges_on_login(self):
        cat = Category.objects.create(slug="c", name="c")
        sh = Shop.objects.create(name="Z", status=Shop.ACTIVE)
        p = Product.objects.create(shop=sh, category=cat, name="P")
        v = Variant.objects.create(product=p, name="m", price=1000, stock=5)
        u = mk_user("kh", Profile.CUSTOMER)
        c = Client()
        c.post(reverse("cart_add"), {"variant": v.pk, "qty": 2})
        self.assertFalse(CartItem.objects.exists())
        c.post(reverse("login"), {"identifier": "kh", "password": "abc12345"})
        self.assertEqual(CartItem.objects.get(user=u).qty, 2)


class OrderTests(Base):
    def test_split_orders_stock_and_coupons(self):
        g = self.order(global_code="TOANSAN", shop_codes={self.s1.pk: "SHOP1"})
        self.assertEqual(g.orders.count(), 2)
        o1, o2 = g.orders.order_by("shop_id")
        self.assertEqual((o1.subtotal, o2.subtotal), (600000, 200000))
        # mã toàn sàn: 10% của 800000 = 80000, tối đa 40000, phân bổ 30000 / 10000
        self.assertEqual((o1.global_discount, o2.global_discount), (30000, 10000))
        self.assertEqual(o1.shop_discount, 20000)
        self.assertEqual(o1.total, 600000 - 50000 + 30000)
        self.assertEqual(g.total, o1.total + o2.total)
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual((self.a.stock, self.b.stock), (8, 4))
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 0)
        self.gc.refresh_from_db(); self.sc.refresh_from_db()
        self.assertEqual((self.gc.used_count, self.sc.used_count), (1, 1))

    def test_oversell_and_bad_coupon_rollback(self):
        with self.assertRaises(OrderError):
            services.place_order(self.cust, {self.a.pk: 11}, {"name": "A", "phone": "1", "address": "x"}, "COD")
        with self.assertRaises(OrderError):
            self.order(shop_codes={self.s2.pk: "SHOP1"})          # mã của gian hàng khác
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        self.assertEqual(Order.objects.count(), 0)

    def test_coupon_max_uses(self):
        self.gc.max_uses = 1; self.gc.save()
        self.order(global_code="TOANSAN")
        CartItem.objects.create(user=self.cust, variant=self.a, qty=1)
        with self.assertRaises(OrderError):
            services.place_order(self.cust, {self.a.pk: 1}, {"name": "A", "phone": "1", "address": "x"}, "COD", global_code="TOANSAN")

    def test_customer_cancel_pending_restores_stock_and_coupon(self):
        g = self.order(global_code="TOANSAN", shop_codes={self.s1.pk: "SHOP1"})
        o1, o2 = g.orders.order_by("shop_id")
        self.assertEqual(services.customer_cancel(self.cust, o1.pk, "đổi ý"), "DA_HUY")
        self.a.refresh_from_db(); self.sc.refresh_from_db(); self.gc.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        self.assertEqual(self.sc.used_count, 0)
        self.assertEqual(self.gc.used_count, 1)                   # đơn thứ hai còn dùng mã toàn sàn
        services.customer_cancel(self.cust, o2.pk, "đổi ý")
        self.gc.refresh_from_db()
        self.assertEqual(self.gc.used_count, 0)                   # mọi đơn của nhóm đã hủy -> hoàn lượt
        with self.assertRaises(OrderError):
            services.customer_cancel(self.cust, o2.pk, "lại")

    def test_confirmed_cancel_request_flow_and_shipping_rules(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        with self.assertRaises(OrderError):
            services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "X1")     # bỏ qua bước
        with self.assertRaises(OrderError):
            services.update_status(self.v2u, o.pk, Order.CONFIRMED)                 # đơn của gian hàng khác
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        self.assertEqual(services.customer_cancel(self.cust, o.pk, "đổi ý"), "DA_GUI")
        with self.assertRaises(OrderError):
            services.customer_cancel(self.cust, o.pk, "lần hai")
        with self.assertRaises(OrderError):
            services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "X1")     # còn yêu cầu hủy
        with self.assertRaises(OrderError):
            services.vendor_resolve_cancel(self.v1u, o.pk, False, "")               # từ chối phải có lý do
        services.vendor_resolve_cancel(self.v1u, o.pk, False, "đã đóng gói")
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "X1")
        with self.assertRaises(OrderError):
            services.customer_cancel(self.cust, o.pk, "muộn rồi")                   # đang giao
        o2 = g.orders.get(shop=self.s2)
        services.update_status(self.v2u, o2.pk, Order.CONFIRMED)
        with self.assertRaises(OrderError):
            services.update_status(self.v2u, o2.pk, Order.SHIPPING, "ghn", "X1")    # trùng mã vận đơn (không phân biệt hoa thường)

    def test_auto_accept_and_auto_complete(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.customer_cancel(self.cust, o.pk, "đổi ý")
        from shopping.models import CancelRequest
        CancelRequest.objects.update(created=timezone.now() - timedelta(hours=25))
        self.assertEqual(services.run_timeouts()[0], 1)
        self.assertEqual(services.run_timeouts(), (0, 0))                           # chạy lại không xử lý trùng
        o.refresh_from_db(); self.assertEqual(o.status, Order.CANCELED)
        o2 = g.orders.get(shop=self.s2)
        services.update_status(self.v2u, o2.pk, Order.CONFIRMED)
        services.update_status(self.v2u, o2.pk, Order.SHIPPING, "GHN", "A1")
        Order.objects.filter(pk=o2.pk).update(shipped_at=timezone.now() - timedelta(days=8))
        self.assertEqual(services.run_timeouts()[1], 1)
        o2.refresh_from_db(); self.assertEqual(o2.status, Order.DONE); self.assertEqual(o2.payment_status, Order.PAID)

    def test_review_rules_and_stats(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        pid = self.p1.pk
        with self.assertRaises(OrderError):
            services.create_review(self.cust, o.pk, pid, 5, "ok")                   # chưa hoàn thành
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "R1")
        with self.assertRaises(OrderError):
            services.update_status(self.v1u, o.pk, Order.DONE)                      # người bán không tự hoàn thành
        services.confirm_received(self.cust, o.pk)
        for bad in (0, 6, "x"):
            with self.assertRaises(OrderError):
                services.create_review(self.cust, o.pk, pid, bad)
        services.create_review(self.cust, o.pk, pid, 4, "tốt")
        with self.assertRaises(OrderError):
            services.create_review(self.cust, o.pk, pid, 5)                         # chỉ một lần
        with self.assertRaises(OrderError):
            services.create_review(self.cust, o.pk, self.p2.pk, 5)                  # không có trong đơn
        self.assertEqual(Review.objects.count(), 1)
        from catalog.models import BehaviorLog
        self.assertTrue(BehaviorLog.objects.filter(user=self.cust, product=self.p1, type="PURCHASE").exists())
        today = timezone.localdate()
        rows = reports.stats(today, today, Shop.objects.order_by("pk"))
        self.assertEqual((rows[0]["done"], rows[0]["revenue"]), (1, 600000))        # không tính phí vận chuyển
        self.assertEqual(rows[1]["done"], 0)
        with self.assertRaises(reports.ReportError):
            reports.stats(today, today + timedelta(days=1), Shop.objects.all())

    def test_vendor_cancel_needs_reason_and_stats_split(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        with self.assertRaises(OrderError):
            services.vendor_cancel(self.v1u, o.pk, " ")
        services.vendor_cancel(self.v1u, o.pk, "hết hàng")
        today = timezone.localdate()
        row = reports.stats(today, today, Shop.objects.filter(pk=self.s1.pk))[0]
        self.assertEqual((row["cancel_manual"], row["cancel_auto"]), (1, 0))


class ViewTests(Base):
    def test_checkout_via_http_and_permissions(self):
        c = Client()
        self.assertEqual(c.get(reverse("checkout")).status_code, 302)               # chưa đăng nhập
        c.login(username="ban1", password="abc12345")
        self.assertEqual(c.get(reverse("checkout")).status_code, 403)               # người bán không mua hàng
        c.logout(); c.login(username="khach", password="abc12345")
        r = c.get(reverse("checkout")); self.assertContains(r, "Tai nghe A")
        r = c.post(reverse("checkout"), {"name": "A", "phone": "0900", "address": "HCM", "payment_method": "COD",
                                         "global_code": "TOANSAN", "action": "apply"})
        self.assertContains(r, "Đã áp mã TOANSAN")
        r = c.post(reverse("checkout"), {"name": "A", "phone": "0900", "address": "HCM", "payment_method": "COD",
                                         "global_code": "", "action": "place"})
        self.assertEqual(r.status_code, 302)
        self.assertContains(c.get(reverse("my_orders")), "Đơn #")
        o = Order.objects.first()
        self.assertEqual(c.get(reverse("order_detail", args=[o.pk])).status_code, 200)
        c2 = Client(); c2.login(username="ban2", password="abc12345")
        self.assertEqual(c2.get(reverse("vendor_order_detail", args=[o.pk])).status_code, 404 if o.shop_id == self.s1.pk else 200)
        for name in ("stats", "coupons", "manage_home", "vendor_orders"):
            self.assertEqual(c2.get(reverse(name)).status_code, 200)
        cc = Client(); cc.login(username="adm", password="abc12345")
        self.assertContains(cc.get(reverse("stats")), "Doanh thu")
        self.assertEqual(c.get(reverse("stats")).status_code, 403)                   # khách không xem thống kê

    def test_coupon_create_via_http(self):
        c = Client(); c.login(username="ban1", password="abc12345")
        r = c.post(reverse("coupons"), {"code": "moi10", "kind": "PHAN_TRAM", "value": 10, "min_order": 0,
                                        "starts": "2026-01-01T00:00", "expires": "2026-12-31T00:00", "max_uses": 5})
        self.assertEqual(r.status_code, 302)
        cp = Coupon.objects.get(code="MOI10"); self.assertEqual((cp.scope, cp.shop), ("GIAN_HANG", self.s1))
        r = c.post(reverse("coupons"), {"code": "MOI10", "kind": "PHAN_TRAM", "value": 10, "min_order": 0,
                                        "starts": "2026-01-01T00:00", "expires": "2026-12-31T00:00", "max_uses": 5})
        self.assertContains(r, "đã tồn tại")
        r = c.post(reverse("coupons"), {"code": "BAD", "kind": "PHAN_TRAM", "value": 10, "min_order": 0,
                                        "starts": "2026-05-01T00:00", "expires": "2026-04-01T00:00", "max_uses": 5})
        self.assertContains(r, "sau ngày bắt đầu")

    def test_chatbot_flow_persists_masks_and_refuses(self):
        c = Client(); c.login(username="khach", password="abc12345")
        post = lambda m, **k: c.post(reverse("chatbot"), {"message": m, **k}, content_type="application/json")  # noqa: E731
        r = post("Tai nghe A giá bao nhiêu? sdt 0912345678 mail a@b.vn").json()
        self.assertEqual(r["status"], "OK"); self.assertIn("300.000", r["answer"])
        log = ChatLog.objects.latest("id")
        self.assertNotIn("0912345678", log.question); self.assertNotIn("a@b.vn", log.question)
        self.assertEqual(post("hôm nay thời tiết thế nào").json()["status"], "TU_CHOI")
        self.assertEqual(post("x" * 400).status_code, 400)
        self.assertIn("giá", c.get(reverse("chatbot_history")).json()["messages"][0]["q"])
        r = post("còn hàng không", product_id=self.p2.pk).json(); self.assertIn("Sạc B", r["answer"])
        self.p1.status = Product.REMOVED; self.p1.removal_reason = "vi phạm"; self.p1.save()
        self.assertEqual(post("Tai nghe A giá bao nhiêu").json()["status"], "TU_CHOI")   # sản phẩm bị gỡ không được tư vấn
        for _ in range(10):
            last = post("sạc giá")
        self.assertEqual(last.status_code, 429)                                       # giới hạn tần suất

    def test_home_search_product_pages_render(self):
        c = Client()
        for url in ("/", "/tim-kiem/?q=tai", self.p1.get_absolute_url(), reverse("cart"), reverse("login"), reverse("register")):
            self.assertEqual(c.get(url).status_code, 200, url)
