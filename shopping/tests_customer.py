"""Kiểm thử module Khách hàng (v6): chi tiết đơn, danh sách đơn có lọc, mua lại, đánh giá của tôi,
thông báo, hồ sơ + đổi mật khẩu, giỏ hàng / checkout."""
from django.test import Client
from django.urls import reverse

from accounts.models import Profile
from catalog.models import Product
from shopping import services
from shopping.models import CartItem, Notification, Order, OrderGroup, Review

from .tests import Base, mk_user

INFO = {"name": "An", "phone": "0900000000", "address": "12 Lê Lợi, HCM"}


class CustomerBase(Base):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.login(username="khach", password="abc12345")

    def place(self, method="COD", **kw):
        CartItem.objects.filter(user=self.cust).delete()
        return services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1}, INFO, method, **kw)

    def done_order(self, shop_user=None, order=None):
        """Đưa đơn của gian hàng 1 tới Hoàn thành."""
        g = self.place()
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "CUST-1")
        services.confirm_received(self.cust, o.pk)
        o.refresh_from_db()
        return o


# ------------------------------------------------------------ chi tiết đơn hàng
class OrderDetailTests(CustomerBase):
    def test_detail_shows_items_money_shipping_and_progress(self):
        g = self.place(global_code="TOANSAN", shop_codes={self.s1.pk: "SHOP1"})
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "MV-123")
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Tai nghe A")
        self.assertContains(r, "MV-123")                       # mã vận đơn
        self.assertContains(r, "SHOP1")                        # mã giảm giá gian hàng
        self.assertContains(r, "TOANSAN")                      # mã giảm giá toàn sàn
        self.assertContains(r, "Đã nhận hàng")                 # đơn Đang giao
        self.assertContains(r, "12 Lê Lợi, HCM")
        self.assertContains(r, "Đơn khác cùng lần đặt")        # đơn của gian hàng 2
        steps = r.context["steps"]
        self.assertEqual([s["state"] for s in steps], ["done", "done", "current", "todo"])
        self.assertTrue(all(s["at"] for s in steps[:3]))       # mốc đã qua có thời điểm

    def test_timeline_uses_vietnamese_labels_not_raw_codes(self):
        o = self.done_order()
        html = self.c.get(reverse("order_detail", args=[o.pk])).content.decode()
        tl = html[html.index('class="timeline"'):]
        tl = tl[:tl.index("</ul>")]
        for raw in ("CHO_XAC_NHAN", "DA_XAC_NHAN", "DANG_GIAO", "HOAN_THANH"):
            self.assertNotIn(raw, tl)
        self.assertIn("Đang giao", tl)
        self.assertIn("(khach)", tl)                                           # người thực hiện hiện tên

    def test_canceled_order_shows_cancel_step_reason_and_refund_note(self):
        g = self.place()
        o = g.orders.get(shop=self.s1)
        services.customer_cancel(self.cust, o.pk, "Đổi ý")
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, "Đổi ý")
        self.assertEqual(r.context["steps"][-1]["state"], "cancel")
        self.assertNotContains(r, "Hủy đơn</button>")          # đơn đã hủy không còn form hủy
        o.refresh_from_db()
        o.payment_status = Order.REFUND_WAIT
        o.save(update_fields=["payment_status"])
        self.assertContains(self.c.get(reverse("order_detail", args=[o.pk])), "chờ hoàn tiền")

    def test_online_unpaid_shows_pay_button_amount_and_hold(self):
        g = self.place("CONG_THANH_TOAN")
        o = g.orders.get(shop=self.s1)
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertTrue(r.context["can_pay"])
        self.assertEqual(r.context["pay_amount"], g.total)        # thanh toán cho cả nhóm
        self.assertEqual(r.context["pay_orders"], 2)
        self.assertContains(r, reverse("pay_group", args=[g.pk]))
        self.assertContains(r, "Kho được giữ đến")

    def test_cod_detail_has_no_pay_button(self):
        o = self.place().orders.get(shop=self.s1)
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertFalse(r.context["can_pay"])
        self.assertContains(r, "Thanh toán khi nhận hàng")

    def test_cancel_request_history_is_shown(self):
        g = self.place()
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.customer_cancel(self.cust, o.pk, "Muốn đổi địa chỉ")
        self.assertContains(self.c.get(reverse("order_detail", args=[o.pk])), "Đang chờ Người bán xử lý")
        services.vendor_resolve_cancel(self.v1u, o.pk, False, "Đã đóng gói")
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, "Bị từ chối")
        self.assertContains(r, "Đã đóng gói")

    def test_review_form_then_review_displayed_in_detail(self):
        o = self.done_order()
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, reverse("review_create", args=[o.pk, self.p1.pk]))
        self.c.post(reverse("review_create", args=[o.pk, self.p1.pk]), {"rating": "4", "comment": "Âm thanh tốt"})
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, "Âm thanh tốt")
        self.assertNotContains(r, reverse("review_create", args=[o.pk, self.p1.pk]))

    def test_hidden_product_shows_as_stopped_and_no_link(self):
        o = self.place().orders.get(shop=self.s1)
        self.p1.status = Product.HIDDEN
        self.p1.save()
        r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, "đã ngừng bán")
        self.assertNotContains(r, f'href="{self.p1.get_absolute_url()}"')

    def test_access_control(self):
        o = self.place().orders.get(shop=self.s1)
        url = reverse("order_detail", args=[o.pk])
        anon = Client()
        self.assertEqual(anon.get(url).status_code, 302)                      # chưa đăng nhập
        other = mk_user("khach2", Profile.CUSTOMER)
        c2 = Client(); c2.login(username="khach2", password="abc12345")
        self.assertEqual(c2.get(url).status_code, 404)                        # đơn của người khác
        cv = Client(); cv.login(username="ban1", password="abc12345")
        self.assertEqual(cv.get(url).status_code, 403)                        # người bán không vào trang khách
        self.assertEqual(self.c.get(reverse("order_detail", args=[999999])).status_code, 404)
        self.assertIsNotNone(other)


# ---------------------------------------------------------------- danh sách đơn
class MyOrdersTests(CustomerBase):
    def test_tabs_filter_by_status_and_counts(self):
        g1 = self.place()
        g2 = self.place()
        services.customer_cancel(self.cust, g2.orders.get(shop=self.s1).pk, "Đổi ý")
        r = self.c.get(reverse("my_orders"))
        counts = {k: n for k, _l, n in r.context["tabs"]}
        self.assertEqual(counts[""], 4)
        self.assertEqual(counts["DA_HUY"], 1)
        self.assertEqual(counts["CHO_XAC_NHAN"], 3)
        r = self.c.get(reverse("my_orders"), {"trang_thai": "DA_HUY"})
        shown = [o.pk for g in r.context["groups"] for o in g.shown]
        self.assertEqual(shown, [g2.orders.get(shop=self.s1).pk])             # chỉ hiện đơn đã hủy
        self.assertNotIn(g1.pk, [g.pk for g in r.context["groups"]])

    def test_search_by_order_id_group_id_product_and_shop(self):
        g = self.place()
        o1 = g.orders.get(shop=self.s1)
        for q, expect in ((str(o1.pk), True), (f"#{o1.pk}", True), ("Sạc B", True), ("S2", True), ("không có gì", False)):
            r = self.c.get(reverse("my_orders"), {"q": q})
            self.assertEqual(bool(r.context["groups"]), expect, q)
        r = self.c.get(reverse("my_orders"), {"q": "Tai nghe"})
        self.assertEqual([o.shop_id for o in r.context["groups"][0].shown], [self.s1.pk])   # chỉ đơn khớp

    def test_pagination_and_page_query_keeps_filter(self):
        self.a.stock = self.b.stock = 100
        self.a.save(); self.b.save()
        for _ in range(12):
            self.place()
        r = self.c.get(reverse("my_orders"), {"trang_thai": "CHO_XAC_NHAN"})
        self.assertEqual(r.context["page"].paginator.count, 12)
        self.assertEqual(len(r.context["groups"]), 10)
        self.assertContains(r, "trang_thai=CHO_XAC_NHAN&amp;trang=2")
        r2 = self.c.get(reverse("my_orders"), {"trang_thai": "CHO_XAC_NHAN", "trang": 2})
        self.assertEqual(len(r2.context["groups"]), 2)

    def test_unpaid_tab_and_pay_button(self):
        self.place("COD")
        g = self.place("CONG_THANH_TOAN")
        r = self.c.get(reverse("my_orders"), {"trang_thai": "cho_thanh_toan"})
        self.assertEqual([x.pk for x in r.context["groups"]], [g.pk])
        self.assertContains(r, reverse("pay_group", args=[g.pk]))
        self.assertFalse(r.context["groups"][0].shown[0].payment_status == Order.PAID)

    def test_does_not_leak_other_customers_orders(self):
        self.place()
        mk_user("khach2", Profile.CUSTOMER)
        c2 = Client(); c2.login(username="khach2", password="abc12345")
        r = c2.get(reverse("my_orders"))
        self.assertContains(r, "Chưa có đơn hàng")
        self.assertEqual(len(r.context["groups"]), 0)

    def test_invalid_status_param_is_ignored(self):
        self.place()
        r = self.c.get(reverse("my_orders"), {"trang_thai": "XYZ'; DROP"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["status"], "")
        self.assertEqual(len(r.context["groups"]), 1)


# ---------------------------------------------------------------------- mua lại
class ReorderTests(CustomerBase):
    def test_reorder_adds_items_to_cart(self):
        o = self.place().orders.get(shop=self.s1)
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 0)
        r = self.c.post(reverse("order_reorder", args=[o.pk]))
        self.assertRedirects(r, reverse("cart"))
        item = CartItem.objects.get(user=self.cust, variant=self.a)
        self.assertEqual(item.qty, 2)

    def test_reorder_caps_at_stock_and_skips_stopped_products(self):
        o = self.place().orders.get(shop=self.s1)
        self.a.refresh_from_db()
        self.a.stock = 1
        self.a.save()
        r = self.c.post(reverse("order_reorder", args=[o.pk]), follow=True)
        self.assertEqual(CartItem.objects.get(user=self.cust, variant=self.a).qty, 1)
        self.assertContains(r, "chỉ thêm 1/2")
        CartItem.objects.all().delete()
        self.p1.status = Product.HIDDEN
        self.p1.save()
        r = self.c.post(reverse("order_reorder", args=[o.pk]), follow=True)
        self.assertEqual(CartItem.objects.filter(user=self.cust).count(), 0)
        self.assertContains(r, "đã ngừng bán")

    def test_reorder_rules(self):
        o = self.place().orders.get(shop=self.s1)
        url = reverse("order_reorder", args=[o.pk])
        self.assertEqual(self.c.get(url).status_code, 405)                    # chỉ nhận POST
        mk_user("khach2", Profile.CUSTOMER)
        c2 = Client(); c2.login(username="khach2", password="abc12345")
        self.assertEqual(c2.post(url).status_code, 404)                       # đơn của người khác


# ---------------------------------------------------------------- đánh giá của tôi
class MyReviewsTests(CustomerBase):
    def test_pending_only_from_completed_orders(self):
        g = self.place()                                                      # chưa hoàn thành
        self.assertEqual(self.c.get(reverse("my_reviews")).context["pending"], [])
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        services.update_status(self.v1u, o.pk, Order.SHIPPING, "GHN", "RV-1")
        services.confirm_received(self.cust, o.pk)
        r = self.c.get(reverse("my_reviews"))
        self.assertEqual([i.product.pk for i in r.context["pending"]], [self.p1.pk])
        self.assertContains(r, "Gửi đánh giá")

    def test_submit_from_my_reviews_returns_there_and_moves_to_done_tab(self):
        o = self.done_order()
        r = self.c.post(reverse("review_create", args=[o.pk, self.p1.pk]), {"rating": "5", "comment": "Tuyệt", "from": "reviews"})
        self.assertRedirects(r, reverse("my_reviews"))
        self.assertEqual(Review.objects.get().rating, 5)
        self.assertEqual(self.c.get(reverse("my_reviews")).context["pending"], [])
        r = self.c.get(reverse("my_reviews"), {"tab": "da"})
        self.assertContains(r, "Tuyệt")
        self.assertEqual(r.context["n_reviewed"], 1)

    def test_invalid_rating_shows_error_and_keeps_pending(self):
        o = self.done_order()
        r = self.c.post(reverse("review_create", args=[o.pk, self.p1.pk]), {"rating": "9", "from": "reviews"}, follow=True)
        self.assertContains(r, "Số sao phải là số nguyên từ 1 đến 5")
        self.assertEqual(Review.objects.count(), 0)

    def test_only_own_reviews_listed(self):
        o = self.done_order()
        services.create_review(self.cust, o.pk, self.p1.pk, 3, "của khách 1")
        mk_user("khach2", Profile.CUSTOMER)
        c2 = Client(); c2.login(username="khach2", password="abc12345")
        self.assertNotContains(c2.get(reverse("my_reviews"), {"tab": "da"}), "của khách 1")


# -------------------------------------------------------------------- thông báo
class NotificationTests(CustomerBase):
    def setUp(self):
        super().setUp()
        Notification.objects.filter(user=self.cust).delete()
        self.n1 = Notification.objects.create(user=self.cust, content="Đơn #1 đã xác nhận", link="/don-hang/1/")
        self.n2 = Notification.objects.create(user=self.cust, content="Thông báo không link")

    def test_list_does_not_auto_mark_read(self):
        r = self.c.get(reverse("notifications"))
        self.assertEqual(r.context["unread_total"], 2)
        self.n1.refresh_from_db()
        self.assertFalse(self.n1.read)

    def test_open_marks_read_and_redirects_to_link(self):
        r = self.c.get(reverse("notification_open", args=[self.n1.pk]))
        self.assertRedirects(r, "/don-hang/1/", fetch_redirect_response=False)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.read)
        r = self.c.get(reverse("notification_open", args=[self.n2.pk]))
        self.assertRedirects(r, reverse("notifications"))                      # không có link: về danh sách

    def test_open_never_redirects_off_site(self):
        for bad in ("//evil.example.com/x", "https://evil.example.com", "javascript:alert(1)", "/\\evil.com"):
            n = Notification.objects.create(user=self.cust, content="x", link=bad)
            r = self.c.get(reverse("notification_open", args=[n.pk]))
            self.assertRedirects(r, reverse("notifications"), msg_prefix=bad)

    def test_cannot_open_someone_elses_notification(self):
        other = mk_user("khach2", Profile.CUSTOMER)
        n = Notification.objects.create(user=other, content="riêng tư", link="/don-hang/9/")
        self.assertEqual(self.c.get(reverse("notification_open", args=[n.pk])).status_code, 404)
        n.refresh_from_db()
        self.assertFalse(n.read)

    def test_read_all_only_touches_own_and_requires_post(self):
        other = mk_user("khach2", Profile.CUSTOMER)
        theirs = Notification.objects.create(user=other, content="của khách 2")
        self.assertEqual(self.c.get(reverse("notifications_read_all")).status_code, 405)
        self.c.post(reverse("notifications_read_all"))
        self.assertEqual(Notification.objects.filter(user=self.cust, read=False).count(), 0)
        theirs.refresh_from_db()
        self.assertFalse(theirs.read)

    def test_unread_filter(self):
        self.c.get(reverse("notification_open", args=[self.n1.pk]))
        r = self.c.get(reverse("notifications"), {"chua_doc": "1"})
        self.assertEqual([n.pk for n in r.context["items"]], [self.n2.pk])

    def test_anonymous_is_redirected_to_login(self):
        for name in ("notifications",):
            self.assertEqual(Client().get(reverse(name)).status_code, 302)
        self.assertEqual(Client().post(reverse("notifications_read_all")).status_code, 302)


# ------------------------------------------------------------- hồ sơ, đổi mật khẩu
class ProfileTests(CustomerBase):
    def test_update_profile(self):
        r = self.c.post(reverse("profile"), {"full_name": "Nguyễn An", "phone": "0912 345 678", "default_address": "5 Nguyễn Huệ"})
        self.assertRedirects(r, reverse("profile"))
        self.cust.refresh_from_db()
        self.assertEqual(self.cust.first_name, "Nguyễn An")
        self.assertEqual((self.cust.profile.phone, self.cust.profile.default_address), ("0912345678", "5 Nguyễn Huệ"))

    def test_profile_validation(self):
        r = self.c.post(reverse("profile"), {"full_name": "  ", "phone": "123", "default_address": ""})
        self.assertContains(r, "Trường này là bắt buộc")
        self.assertContains(r, "10-11 chữ số")
        taken = mk_user("0987654321", Profile.CUSTOMER)                       # tài khoản dùng số này để đăng nhập
        r = self.c.post(reverse("profile"), {"full_name": "A", "phone": "0987654321"})
        self.assertContains(r, "đã được tài khoản khác sử dụng")
        self.assertIsNotNone(taken)

    def test_phone_login_account_cannot_change_phone(self):
        u = mk_user("0911222333", Profile.CUSTOMER)
        u.profile.phone = "0911222333"; u.profile.save()
        c = Client(); c.login(username="0911222333", password="abc12345")
        c.post(reverse("profile"), {"full_name": "B", "phone": "0999999999", "default_address": "X"})
        u.refresh_from_db()
        self.assertEqual(u.profile.phone, "0911222333")
        self.assertEqual(u.profile.default_address, "X")

    def test_profile_requires_login(self):
        self.assertEqual(Client().get(reverse("profile")).status_code, 302)

    def test_change_password(self):
        url = reverse("change_password")
        r = self.c.post(url, {"old_password": "sai", "password": "moi12345", "password2": "moi12345"})
        self.assertContains(r, "Mật khẩu hiện tại không đúng")
        r = self.c.post(url, {"old_password": "abc12345", "password": "abcdefgh", "password2": "abcdefgh"})
        self.assertContains(r, "gồm cả chữ và số")
        r = self.c.post(url, {"old_password": "abc12345", "password": "moi12345", "password2": "khac12345"})
        self.assertContains(r, "không khớp")
        r = self.c.post(url, {"old_password": "abc12345", "password": "abc12345", "password2": "abc12345"})
        self.assertContains(r, "phải khác mật khẩu hiện tại")
        r = self.c.post(url, {"old_password": "abc12345", "password": "moi12345", "password2": "moi12345"})
        self.assertRedirects(r, reverse("profile"))
        self.assertEqual(self.c.get(reverse("my_orders")).status_code, 200)    # vẫn đăng nhập
        self.assertTrue(Client().login(username="khach", password="moi12345"))
        self.assertFalse(Client().login(username="khach", password="abc12345"))

    def test_other_session_is_logged_out_after_password_change(self):
        other_device = Client(); other_device.login(username="khach", password="abc12345")
        self.c.post(reverse("change_password"), {"old_password": "abc12345", "password": "moi12345", "password2": "moi12345"})
        self.assertEqual(other_device.get(reverse("my_orders")).status_code, 302)


# ------------------------------------------------------------ giỏ hàng, đặt hàng
class CartCheckoutTests(CustomerBase):
    def test_cart_blocks_checkout_when_over_stock(self):
        CartItem.objects.filter(user=self.cust).delete()
        item = CartItem.objects.create(user=self.cust, variant=self.a, qty=2)
        self.a.stock = 1
        self.a.save()
        r = self.c.get(reverse("cart"))
        self.assertTrue(r.context["has_over"])
        self.assertNotContains(r, f'href="{reverse("checkout")}"')
        self.a.stock = 5
        self.a.save()
        r = self.c.get(reverse("cart"))
        self.assertFalse(r.context["has_over"])
        self.assertContains(r, f'href="{reverse("checkout")}"')
        self.assertIsNotNone(item)

    def test_checkout_prefills_and_saves_default_address(self):
        p = self.cust.profile
        p.default_address, p.phone = "", ""
        p.save()
        data = {"name": "An", "phone": "0933444555", "address": "99 Pasteur", "payment_method": "COD",
                "global_code": "", "action": "place", "save_default": "1"}
        r = self.c.post(reverse("checkout"), data)
        self.assertEqual(r.status_code, 302)
        p.refresh_from_db()
        self.assertEqual((p.default_address, p.phone), ("99 Pasteur", "0933444555"))
        CartItem.objects.create(user=self.cust, variant=self.a, qty=1)
        self.assertContains(self.c.get(reverse("checkout")), "99 Pasteur")

    def test_checkout_without_checkbox_does_not_change_profile(self):
        p = self.cust.profile
        p.default_address = "Cũ"; p.save()
        self.c.post(reverse("checkout"), {"name": "An", "phone": "0933444555", "address": "Mới", "payment_method": "COD",
                                           "global_code": "", "action": "place"})
        p.refresh_from_db()
        self.assertEqual(p.default_address, "Cũ")

    def test_group_total_matches_sum_of_orders_on_detail_pages(self):
        g = self.place(global_code="TOANSAN")
        total = sum(o.total for o in g.orders.all())
        self.assertEqual(g.total, total)
        for o in g.orders.all():
            self.assertContains(self.c.get(reverse("order_detail", args=[o.pk])), "Tổng thanh toán")
        self.assertEqual(OrderGroup.objects.count(), 1)
