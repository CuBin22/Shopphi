"""Kiểm thử phần bổ sung: thanh toán Sandbox, quản lý sản phẩm của Người bán, gỡ/khôi phục sản phẩm, nhật ký quản trị."""
from datetime import timedelta
from urllib.parse import urlencode

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from catalog.models import AdminLog, Keyword, Product, Shop, Variant
from shopping import moderation, payments, services
from shopping.models import Order, OrderGroup, PaymentTransaction
from shopping.services import OrderError

from .tests import Base, mk_user

INFO = {"name": "A", "phone": "0900000000", "address": "HCM"}


class PaymentTests(Base):
    def online_order(self, **kw):
        return services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1}, INFO, "CONG_THANH_TOAN", **kw)

    def callback(self, txn, result="success", **override):
        params = payments.build_callback(txn, result)
        params.update(override)
        return params

    def test_online_order_holds_stock_15_minutes(self):
        g = self.online_order()
        self.assertIsNotNone(g.hold_until)
        self.assertAlmostEqual((g.hold_until - g.created).total_seconds(), 15 * 60, delta=2)
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 8)

    def test_success_marks_all_orders_paid_once(self):
        g = self.online_order()
        txn = payments.create_payment(self.cust, g.pk)
        self.assertEqual(txn.amount, g.total)
        outcome, _ = payments.process_result(self.callback(txn))
        self.assertEqual(outcome, "THANH_CONG")
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.PAID})
        # kết quả trùng bị bỏ qua, không cập nhật lần hai
        outcome, _ = payments.process_result(self.callback(txn))
        self.assertEqual(outcome, "BO_QUA")

    def test_bad_signature_amount_and_group_rejected(self):
        g = self.online_order()
        txn = payments.create_payment(self.cust, g.pk)
        for bad in ({"sig": "0" * 64}, {"amount": "1"}, {"group": "999999"}, {"txn_ref": "TXNKHONGCO"}):
            with self.assertRaises(OrderError):
                payments.process_result(self.callback(txn, **bad))
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.UNPAID})
        txn.refresh_from_db()
        self.assertIsNone(txn.processed_at)

    def test_signed_with_wrong_amount_is_rejected(self):
        g = self.online_order()
        txn = payments.create_payment(self.cust, g.pk)
        forged = {"txn_ref": txn.ref, "group": str(g.pk), "amount": "1000", "status": "SUCCESS"}
        forged["sig"] = payments.sign(forged)     # chữ ký đúng nhưng số tiền không khớp giao dịch
        with self.assertRaises(OrderError):
            payments.process_result(forged)

    def test_failed_payment_can_retry_and_old_txn_superseded(self):
        g = self.online_order()
        t1 = payments.create_payment(self.cust, g.pk)
        outcome, _ = payments.process_result(self.callback(t1, "fail"))
        self.assertEqual(outcome, "THAT_BAI")
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.UNPAID})
        t2 = payments.create_payment(self.cust, g.pk)
        t3 = payments.create_payment(self.cust, g.pk)
        t2.refresh_from_db()
        self.assertEqual(t2.status, PaymentTransaction.SUPERSEDED)
        self.assertEqual(PaymentTransaction.objects.filter(group=g, status=PaymentTransaction.PENDING).count(), 1)
        self.assertEqual(t3.status, PaymentTransaction.PENDING)
        # thanh toán lại không kéo dài hạn giữ kho
        g.refresh_from_db()
        self.assertAlmostEqual((g.hold_until - g.created).total_seconds(), 15 * 60, delta=2)

    def test_expired_hold_cancels_orders_and_restores_stock(self):
        g = self.online_order()
        payments.create_payment(self.cust, g.pk)
        later = g.hold_until + timedelta(seconds=1)
        self.assertEqual(payments.expire_overdue(later), 2)
        self.assertEqual(payments.expire_overdue(later), 0)           # chạy lại không xử lý trùng
        self.assertEqual(set(g.orders.values_list("status", flat=True)), {Order.CANCELED})
        self.a.refresh_from_db(); self.b.refresh_from_db()
        self.assertEqual((self.a.stock, self.b.stock), (10, 5))
        self.assertEqual(PaymentTransaction.objects.get(group=g).status, PaymentTransaction.EXPIRED)
        with self.assertRaises(OrderError):
            payments.create_payment(self.cust, g.pk, now=later)

    def test_late_success_after_expiry_goes_to_refund_wait(self):
        g = self.online_order()
        txn = payments.create_payment(self.cust, g.pk)
        payments.expire_overdue(g.hold_until + timedelta(seconds=1))
        outcome, txn = payments.process_result(self.callback(txn))
        self.assertEqual(outcome, "THANH_TOAN_MUON")
        self.assertEqual((txn.status, txn.refund_status), (PaymentTransaction.LATE, PaymentTransaction.REFUND_WAIT))
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.UNPAID})   # không cập nhật đơn
        services.complete_late_refund(txn.pk, self.admin)
        txn.refresh_from_db()
        self.assertEqual(txn.refund_status, PaymentTransaction.REFUNDED)

    def test_success_from_superseded_txn_is_late(self):
        g = self.online_order()
        old = payments.create_payment(self.cust, g.pk)
        new = payments.create_payment(self.cust, g.pk)
        outcome, _ = payments.process_result(self.callback(new))
        self.assertEqual(outcome, "THANH_CONG")
        outcome, t = payments.process_result(self.callback(old))        # nhóm đã được thanh toán bằng giao dịch khác
        self.assertEqual(outcome, "THANH_TOAN_MUON")
        self.assertEqual(t.refund_status, PaymentTransaction.REFUND_WAIT)

    def test_cancel_unpaid_order_supersedes_txn_and_pays_remaining(self):
        g = self.online_order()
        t1 = payments.create_payment(self.cust, g.pk)
        o1, o2 = g.orders.order_by("shop_id")
        services.customer_cancel(self.cust, o1.pk, "đổi ý")
        t1.refresh_from_db()
        self.assertEqual(t1.status, PaymentTransaction.SUPERSEDED)
        t2 = payments.create_payment(self.cust, g.pk)
        self.assertEqual(t2.amount, o2.total)
        payments.process_result(self.callback(t2))
        o1.refresh_from_db(); o2.refresh_from_db()
        self.assertEqual((o1.payment_status, o2.payment_status), (Order.UNPAID, Order.PAID))

    def test_cancel_paid_order_then_refund(self):
        g = self.online_order()
        txn = payments.create_payment(self.cust, g.pk)
        payments.process_result(self.callback(txn))
        o1 = g.orders.order_by("shop_id").first()
        services.customer_cancel(self.cust, o1.pk, "đổi ý")
        o1.refresh_from_db()
        self.assertEqual(o1.payment_status, Order.REFUND_WAIT)
        services.complete_refund(o1.pk, self.admin)
        o1.refresh_from_db()
        self.assertEqual(o1.payment_status, Order.REFUNDED)

    def test_vendor_cannot_confirm_unpaid_online_order(self):
        g = self.online_order()
        o1 = g.orders.get(shop=self.s1)
        with self.assertRaises(OrderError):
            services.update_status(self.v1u, o1.pk, Order.CONFIRMED)
        txn = payments.create_payment(self.cust, g.pk)
        payments.process_result(self.callback(txn))
        services.update_status(self.v1u, o1.pk, Order.CONFIRMED)

    def test_cod_group_cannot_pay_online(self):
        g = self.order()
        with self.assertRaises(OrderError):
            payments.create_payment(self.cust, g.pk)

    def test_other_customer_cannot_pay_group(self):
        g = self.online_order()
        other = mk_user("khach2", Profile.CUSTOMER)
        with self.assertRaises(OrderError):
            payments.create_payment(other, g.pk)

    def test_run_timeouts_expires_overdue_online_orders(self):
        g = self.online_order()
        services.run_timeouts(now=g.hold_until + timedelta(minutes=1))
        self.assertEqual(set(g.orders.values_list("status", flat=True)), {Order.CANCELED})

    @override_settings(PAYMENT_PROVIDER="sandbox")
    def test_gateway_flow_over_http(self):
        c = Client()
        c.login(username="khach", password="abc12345")
        g = self.online_order()
        r = c.post(reverse("pay_group", args=[g.pk]))
        txn = PaymentTransaction.objects.get(group=g)
        self.assertRedirects(r, reverse("sandbox_gateway", args=[txn.ref]))
        self.assertContains(c.get(reverse("sandbox_gateway", args=[txn.ref])), "SANDBOX")
        r = c.post(reverse("sandbox_gateway", args=[txn.ref]), {"result": "success"})
        self.assertEqual(r.status_code, 302)
        r = c.get(r["Location"])
        self.assertRedirects(r, reverse("order_success", args=[g.pk]))
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.PAID})
        bad = payments.build_callback(txn, "success")
        bad["sig"] = "x" * 64
        c.get(reverse("payment_return") + "?" + urlencode(bad))
        self.assertEqual(PaymentTransaction.objects.get(pk=txn.pk).status, PaymentTransaction.SUCCESS)


class VendorProductTests(Base):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.login(username="ban1", password="abc12345")

    def data(self, **kw):
        d = {"category": self.cat.pk, "name": "Loa mini", "brand": "X", "tags": "loa, bluetooth", "description": "d", "specs": "Pin: 10h",
             "status": Product.VISIBLE,
             "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0", "variants-MAX_NUM_FORMS": "1000",
             "variants-0-name": "Đen", "variants-0-price": "450000", "variants-0-stock": "7"}
        d.update(kw)
        return d

    def test_vendor_adds_product_for_own_shop(self):
        r = self.c.post(reverse("product_add"), self.data())
        self.assertRedirects(r, reverse("product_list"))
        p = Product.objects.get(name="Loa mini")
        self.assertEqual(p.shop, self.s1)
        self.assertEqual((p.variants.get().price, p.variants.get().stock), (450000, 7))

    def test_validation_price_stock_category(self):
        for bad in ({"variants-0-price": "0"}, {"variants-0-stock": "-1"}, {"category": ""}, {"variants-0-price": ""}):
            self.c.post(reverse("product_add"), self.data(**bad))
        self.assertFalse(Product.objects.filter(name="Loa mini").exists())

    def test_product_needs_active_shop(self):
        self.s1.status = Shop.LOCKED
        self.s1.status_reason = "vi phạm"
        self.s1.save()
        r = self.c.post(reverse("product_add"), self.data())
        self.assertRedirects(r, reverse("manage_home"))
        self.assertFalse(Product.objects.filter(name="Loa mini").exists())

    def test_vendor_cannot_touch_other_shop_product(self):
        self.assertEqual(self.c.get(reverse("product_edit", args=[self.p2.pk])).status_code, 404)
        self.assertEqual(self.c.post(reverse("product_toggle", args=[self.p2.pk])).status_code, 404)
        self.c.post(reverse("product_delete", args=[self.p2.pk]))
        self.assertTrue(Product.objects.filter(pk=self.p2.pk).exists())

    def test_toggle_visibility_and_removed_cannot_be_shown(self):
        self.c.post(reverse("product_toggle", args=[self.p1.pk]))
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.status, Product.HIDDEN)
        moderation.remove_product(self.admin, self.p1.pk, "hàng cấm")
        self.c.post(reverse("product_toggle", args=[self.p1.pk]))
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.status, Product.REMOVED)

    def test_delete_soft_when_has_orders_else_hard(self):
        self.order()
        self.assertEqual(services.delete_product(self.v1u, self.p1.pk), "DA_AN")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.status, Product.HIDDEN)
        fresh = Product.objects.create(shop=self.s1, category=self.cat, name="Mới")
        Variant.objects.create(product=fresh, name="m", price=1000, stock=1)
        self.assertEqual(services.delete_product(self.v1u, fresh.pk), "DA_XOA")
        self.assertFalse(Product.objects.filter(pk=fresh.pk).exists())

    def test_cannot_delete_variant_with_orders(self):
        self.order()
        d = self.data(name="Tai nghe A")
        d.update({"variants-TOTAL_FORMS": "2", "variants-INITIAL_FORMS": "1", "variants-0-id": self.a.pk,
                  "variants-0-product": self.p1.pk, "variants-0-name": "Đen", "variants-0-price": "300000",
                  "variants-0-stock": "8", "variants-0-DELETE": "on",
                  "variants-1-name": "Mặc định", "variants-1-price": "", "variants-1-stock": ""})
        self.c.post(reverse("product_edit", args=[self.p1.pk]), d)
        self.assertTrue(Variant.objects.filter(pk=self.a.pk).exists())

    def test_hidden_product_not_sellable_but_listed_for_vendor(self):
        self.c.post(reverse("product_toggle", args=[self.p1.pk]))
        self.assertFalse(Product.objects.sellable().filter(pk=self.p1.pk).exists())
        self.assertContains(self.c.get(reverse("product_list")), "Tai nghe A")


class ModerationTests(Base):
    def test_remove_and_restore_product_with_log_and_notification(self):
        with self.assertRaises(OrderError):
            moderation.remove_product(self.admin, self.p1.pk, "  ")
        with self.assertRaises(OrderError):
            moderation.remove_product(self.v1u, self.p1.pk, "lý do")           # không phải Quản trị viên
        moderation.remove_product(self.admin, self.p1.pk, "Hàng cấm")
        self.p1.refresh_from_db()
        self.assertEqual((self.p1.status, self.p1.removal_reason), (Product.REMOVED, "Hàng cấm"))
        self.assertFalse(Product.objects.sellable().filter(pk=self.p1.pk).exists())
        with self.assertRaises(OrderError):
            moderation.remove_product(self.admin, self.p1.pk, "lại")
        moderation.restore_product(self.admin, self.p1.pk, "Đã khắc phục")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.status, Product.HIDDEN)                      # khôi phục về Ẩn
        self.assertEqual(AdminLog.objects.filter(target_type=AdminLog.PRODUCT).count(), 2)
        self.assertTrue(self.v1u.notifications.filter(content__contains="bị gỡ").exists())

    def test_shop_status_flow_and_reasons(self):
        shop = Shop.objects.create(name="Mới", owner=mk_user("ban9", Profile.VENDOR))
        with self.assertRaises(OrderError):
            moderation.set_shop_status(self.admin, shop.pk, Shop.REJECTED, "")
        moderation.set_shop_status(self.admin, shop.pk, Shop.REJECTED, "Thiếu giấy tờ")
        with self.assertRaises(OrderError):
            moderation.set_shop_status(self.admin, shop.pk, Shop.ACTIVE)        # Từ chối không đi thẳng sang Hoạt động
        shop.refresh_from_db()
        shop.status = Shop.PENDING
        shop.save()
        moderation.set_shop_status(self.admin, shop.pk, Shop.ACTIVE)
        moderation.set_shop_status(self.admin, shop.pk, Shop.LOCKED, "Vi phạm")
        with self.assertRaises(OrderError):
            moderation.set_shop_status(self.admin, shop.pk, Shop.LOCKED, "lại")
        moderation.set_shop_status(self.admin, shop.pk, Shop.ACTIVE)
        self.assertEqual(AdminLog.objects.filter(target_type=AdminLog.SHOP).count(), 4)

    def test_locked_shop_products_not_sellable(self):
        moderation.set_shop_status(self.admin, self.s1.pk, Shop.LOCKED, "Vi phạm")
        self.assertFalse(Product.objects.sellable().filter(pk=self.p1.pk).exists())

    def test_keyword_hide_requires_reason(self):
        k = Keyword.objects.create(phrase="tai nghe", frequency=5)
        with self.assertRaises(OrderError):
            moderation.set_keyword_visibility(self.admin, k.pk, False, "")
        moderation.set_keyword_visibility(self.admin, k.pk, False, "Không phù hợp")
        k.refresh_from_db()
        self.assertFalse(k.visible)
        moderation.set_keyword_visibility(self.admin, k.pk, True)
        self.assertEqual(AdminLog.objects.filter(target_type=AdminLog.KEYWORD).count(), 2)

    def test_admin_pages_only_for_admin(self):
        c = Client()
        c.login(username="ban1", password="abc12345")
        for name in ("admin_shops", "admin_products", "admin_keywords", "refunds", "admin_logs"):
            self.assertEqual(c.get(reverse(name)).status_code, 403, name)
        c = Client()
        c.login(username="adm", password="abc12345")
        for name in ("admin_shops", "admin_products", "admin_keywords", "refunds", "admin_logs"):
            self.assertEqual(c.get(reverse(name)).status_code, 200, name)
