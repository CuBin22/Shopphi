"""Chặn dùng cổng giả lập để tự đánh dấu đã thanh toán khi chạy ZaloPay, và giới hạn tần suất hỏi ZaloPay."""
from unittest import mock

from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

from shopping import payments, services, zalopay
from shopping.models import Order, PaymentTransaction
from shopping.services import OrderError

from .tests import Base

INFO = {"name": "A", "phone": "0900000000", "address": "HCM"}


@override_settings(PAYMENT_PROVIDER="zalopay")
class ZaloPayGuardTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        self.group, self.txn = g, payments.create_payment(self.cust, g.pk)

    def make_zalopay(self):
        self.txn.provider, self.txn.app_trans_id = PaymentTransaction.ZALOPAY, f"261024_{self.txn.ref}"
        self.txn.save()

    def test_sandbox_gateway_closed_when_provider_is_zalopay(self):
        self.make_zalopay()
        c = Client()
        c.login(username="khach", password="abc12345")
        self.assertEqual(c.get(reverse("sandbox_gateway", args=[self.txn.ref])).status_code, 404)
        self.assertEqual(c.post(reverse("sandbox_gateway", args=[self.txn.ref]), {"result": "success"}).status_code, 404)
        self.assertEqual(Order.objects.get(group=self.group).payment_status, Order.UNPAID)

    def test_signed_result_rejected_for_zalopay_transaction(self):
        self.make_zalopay()
        with self.assertRaises(OrderError):
            payments.process_result(payments.build_callback(self.txn, "success"))
        self.assertEqual(Order.objects.get(group=self.group).payment_status, Order.UNPAID)

    @override_settings(PAYMENT_PROVIDER="sandbox")
    def test_sandbox_gateway_only_for_its_owner(self):
        other = Client()
        self.assertEqual(other.get(reverse("sandbox_gateway", args=[self.txn.ref])).status_code, 404)   # chưa đăng nhập
        c = Client()
        c.login(username="khach", password="abc12345")
        self.assertEqual(c.get(reverse("sandbox_gateway", args=[self.txn.ref])).status_code, 200)

    def test_reconcile_throttle_calls_zalopay_once(self):
        self.make_zalopay()
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 3}) as post:
            for _ in range(5):
                payments.reconcile_group(self.group.pk, throttle=10)
        self.assertEqual(post.call_count, 1)
