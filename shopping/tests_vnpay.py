"""Kiểm thử tích hợp VNPay: dựng URL ký, IPN/Return URL (chữ ký, số tiền, trùng, đến muộn), hoàn tiền mô phỏng. Không gọi mạng."""
from datetime import timedelta
from urllib.parse import parse_qsl, urlsplit

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from shopping import payments, services, vnpay
from shopping.models import Order, PaymentTransaction
from shopping.services import OrderError

from .tests import Base

INFO = {"name": "A", "phone": "0900000000", "address": "HCM"}
SECRET = "secret-test"


@override_settings(PAYMENT_PROVIDER="vnpay", VNPAY_TMN_CODE="TMN", VNPAY_HASH_SECRET=SECRET,
                   VNPAY_URL="https://sandbox.vnpayment.vn/paymentv2/vpcpay.html", VNPAY_RETURN_URL="")
class VnpayTests(Base):
    def new_txn(self):
        g = services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        payments.start_vnpay(txn)
        txn.refresh_from_db()
        return g, txn

    def result(self, txn, amount=None, code="00", status="00", sign=True, **extra):
        p = {"vnp_TmnCode": "TMN", "vnp_Amount": int(txn.amount) * 100 if amount is None else amount, "vnp_TxnRef": txn.ref,
             "vnp_TransactionNo": "14012345", "vnp_ResponseCode": code, "vnp_TransactionStatus": status,
             "vnp_PayDate": vnpay.vn_date(timezone.now())}
        p.update(extra)
        p["vnp_SecureHash"] = vnpay.sign(p, SECRET) if sign else "0" * 128
        return p

    def paid_set(self, g):
        return set(g.orders.values_list("payment_status", flat=True))

    def test_payment_url_is_signed_and_amount_times_100(self):
        g, txn = self.new_txn()
        self.assertEqual(txn.provider, "VNPAY")
        parts = urlsplit(txn.order_url)
        self.assertEqual(parts.netloc, "sandbox.vnpayment.vn")
        q = dict(parse_qsl(parts.query))
        self.assertTrue(vnpay.verify(q, SECRET))
        self.assertEqual((q["vnp_TxnRef"], q["vnp_Amount"], q["vnp_TmnCode"]), (txn.ref, str(int(txn.amount) * 100), "TMN"))
        self.assertEqual(q["vnp_ExpireDate"], vnpay.vn_date(g.hold_until))

    @override_settings(VNPAY_TMN_CODE="", VNPAY_HASH_SECRET="")
    def test_missing_config_raises_clear_error(self):
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        with self.assertRaises(OrderError):
            payments.start_vnpay(txn)

    def test_pay_group_view_redirects_to_vnpay(self):
        c = Client()
        c.login(username="khach", password="abc12345")
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        r = c.post(reverse("pay_group", args=[g.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?"))

    def test_valid_ipn_marks_orders_paid_once(self):
        g, txn = self.new_txn()
        c = Client(enforce_csrf_checks=True)
        r = c.get(reverse("vnpay_ipn"), self.result(txn))
        self.assertEqual(r.json()["RspCode"], "00")
        self.assertEqual(self.paid_set(g), {Order.PAID})
        txn.refresh_from_db()
        self.assertEqual((txn.status, txn.zp_trans_id), (PaymentTransaction.SUCCESS, 14012345))
        r = c.get(reverse("vnpay_ipn"), self.result(txn))
        self.assertEqual(r.json()["RspCode"], "02")                 # trùng, không cập nhật lại

    def test_bad_signature_amount_or_unknown_ref_rejected(self):
        g, txn = self.new_txn()
        self.assertEqual(payments.process_vnpay(self.result(txn, sign=False))[0], "97")
        self.assertEqual(payments.process_vnpay(self.result(txn, amount=100))[0], "04")
        self.assertEqual(payments.process_vnpay(self.result(txn, amount=int(txn.amount) * 100 + 1))[0], "04")
        self.assertEqual(payments.process_vnpay(self.result(txn, vnp_TxnRef="TXNNOPE"))[0], "01")
        self.assertEqual(self.paid_set(g), {Order.UNPAID})

    def test_failed_result_keeps_orders_unpaid_and_allows_retry(self):
        g, txn = self.new_txn()
        code, _, outcome, _ = payments.process_vnpay(self.result(txn, code="24", status="02"))
        self.assertEqual((code, outcome), ("00", "THAT_BAI"))
        txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.FAILED)
        self.assertEqual(self.paid_set(g), {Order.UNPAID})
        payments.create_payment(self.cust, g.pk)                    # thanh toán lại trong hạn giữ kho

    def test_return_url_confirms_and_redirects_to_order_page(self):
        g, txn = self.new_txn()
        c = Client()
        c.login(username="khach", password="abc12345")
        r = c.get(reverse("vnpay_return"), self.result(txn))
        self.assertRedirects(r, reverse("order_success", args=[g.pk]))
        self.assertEqual(self.paid_set(g), {Order.PAID})

    def test_success_after_cancel_is_late_payment_and_refund_is_simulated(self):
        g, txn = self.new_txn()
        payments.expire_overdue(g.hold_until + timedelta(seconds=1), reconcile=False)
        late = vnpay.vn_date(g.hold_until + timedelta(minutes=5))
        self.assertEqual(payments.process_vnpay(self.result(txn, vnp_PayDate=late))[0], "00")
        txn.refresh_from_db()
        self.assertEqual((txn.status, txn.refund_status), (PaymentTransaction.LATE, PaymentTransaction.REFUND_WAIT))
        self.assertEqual(payments.refund_late_transaction(txn.pk), "DA_HOAN_TIEN")   # mô phỏng, không gọi VNPay
