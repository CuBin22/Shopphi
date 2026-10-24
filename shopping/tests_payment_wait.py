"""Chống "treo" sau khi thanh toán ZaloPay: tab đặt hàng tự hỏi trạng thái, trang đơn hàng tự đối soát,
bấm thanh toán lại không làm giao dịch đã trả thành "Thanh toán muộn". HTTP tới ZaloPay được giả lập."""
from unittest import mock

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from shopping import payments, services, zalopay
from shopping.models import Order, PaymentTransaction

from .tests import Base
from .tests_zalopay import INFO, KEY1, KEY2, ok_create


def query_reply(code, txn=None):
    def fake(path, fields):
        assert path == "/v2/query"
        if code == 1:
            return {"return_code": 1, "amount": int(txn.amount), "zp_trans_id": 777,
                    "server_time": int(timezone.now().timestamp() * 1000)}
        return {"return_code": code}
    return fake


@override_settings(PAYMENT_PROVIDER="zalopay", ZALOPAY_APP_ID=2553, ZALOPAY_KEY1=KEY1, ZALOPAY_KEY2=KEY2,
                   ZALOPAY_CALLBACK_URL="", ZALOPAY_REDIRECT_URL="",
                   CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}})   # tắt giới hạn tần suất hỏi ZaloPay
class PaymentWaitTests(Base):
    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.login(username="khach", password="abc12345")
        self.g = services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1}, INFO, "CONG_THANH_TOAN")
        self.txn = payments.create_payment(self.cust, self.g.pk)
        with mock.patch.object(zalopay, "_post", side_effect=ok_create):
            payments.start_zalopay(self.txn, redirect_url="http://x/ret/")
        self.txn.refresh_from_db()
        self.url = reverse("payment_status", args=[self.g.pk])

    def paid(self):
        return all(o.payment_status == Order.PAID for o in Order.objects.filter(group=self.g))

    def test_status_pending_while_zalopay_has_not_recorded_payment(self):
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(3)):
            r = self.c.get(self.url)
        self.assertEqual(r.json()["state"], "pending")
        self.assertEqual(r.json()["url"], reverse("order_success", args=[self.g.pk]))
        self.assertFalse(self.paid())

    def test_status_paid_when_zalopay_confirms_even_without_redirect_or_callback(self):
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(1, self.txn)):
            r = self.c.get(self.url)
        self.assertEqual(r.json()["state"], "paid")
        self.assertTrue(self.paid())
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.SUCCESS)

    def test_status_failed_when_zalopay_reports_failure(self):
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(2)):
            self.assertEqual(self.c.get(self.url).json()["state"], "failed")

    def test_status_survives_zalopay_outage(self):
        with mock.patch.object(zalopay, "_post", side_effect=zalopay.ZaloPayError("timeout")):
            r = self.c.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "pending")

    def test_status_is_private_get_only_and_login_required(self):
        self.assertEqual(Client().get(self.url).status_code, 302)
        self.assertEqual(self.c.post(self.url).status_code, 405)
        from accounts.models import Profile
        from .tests import mk_user
        mk_user("khach2", Profile.CUSTOMER)
        c2 = Client(); c2.login(username="khach2", password="abc12345")
        self.assertEqual(c2.get(self.url).status_code, 404)

    def test_status_canceled_when_all_orders_canceled(self):
        for o in Order.objects.filter(group=self.g):
            services.customer_cancel(self.cust, o.pk, "Đổi ý")
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(3)):
            self.assertEqual(self.c.get(self.url).json()["state"], "canceled")

    def test_opening_my_orders_reconciles_stuck_payment(self):
        PaymentTransaction.objects.filter(pk=self.txn.pk).update(created=timezone.now() - timezone.timedelta(minutes=2))
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(1, self.txn)):
            self.c.get(reverse("my_orders"))
        self.assertTrue(self.paid())

    def test_opening_order_detail_reconciles_stuck_payment(self):
        PaymentTransaction.objects.filter(pk=self.txn.pk).update(created=timezone.now() - timezone.timedelta(minutes=2))
        o = Order.objects.filter(group=self.g).first()
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(1, self.txn)):
            r = self.c.get(reverse("order_detail", args=[o.pk]))
        self.assertContains(r, "Đã thanh toán")
        self.assertTrue(self.paid())

    def test_pay_again_after_stuck_payment_does_not_create_late_payment(self):
        """Khách đã trả tiền nhưng trang ZaloPay treo, bấm Thanh toán lại: phải chốt đơn là Đã thanh toán, không tạo giao dịch mới."""
        with mock.patch.object(zalopay, "_post", side_effect=query_reply(1, self.txn)):
            r = self.c.post(reverse("pay_group", args=[self.g.pk]), follow=True)
        self.assertTrue(self.paid())
        self.assertEqual(PaymentTransaction.objects.filter(group=self.g).count(), 1)
        self.txn.refresh_from_db()
        self.assertEqual(self.txn.status, PaymentTransaction.SUCCESS)
        self.assertContains(r, "không còn đơn nào cần thanh toán")

    def test_pay_again_when_unpaid_creates_new_transaction(self):
        with mock.patch.object(zalopay, "_post", side_effect=lambda p, f: query_reply(3)(p, f) if p == "/v2/query" else ok_create(p, f)):
            r = self.c.post(reverse("pay_group", args=[self.g.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PaymentTransaction.objects.filter(group=self.g).count(), 2)

    def test_pay_forms_open_new_tab_and_carry_status_url(self):
        r = self.c.get(reverse("order_success", args=[self.g.pk]))
        self.assertContains(r, 'target="_blank"')
        self.assertContains(r, f'data-status-url="{self.url}"')
