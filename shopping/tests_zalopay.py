"""Kiểm thử tích hợp ZaloPay: tạo đơn, callback, truy vấn/đối soát, hoàn tiền. HTTP tới ZaloPay được giả lập bằng mock `zalopay._post`."""
import json
from datetime import timedelta
from unittest import mock

from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from shopping import payments, services, zalopay
from shopping.models import Order, PaymentTransaction, RefundRecord
from shopping.services import OrderError

from .tests import Base

INFO = {"name": "A", "phone": "0900000000", "address": "HCM"}
KEY1, KEY2 = "k1-test", "k2-test"


def ok_create(path, fields):
    assert path == "/v2/create"
    return {"return_code": 1, "return_message": "ok", "order_url": "https://qcgateway.zalopay.vn/openinapp?order=abc",
            "zp_trans_token": "tok"}


@override_settings(PAYMENT_PROVIDER="zalopay", ZALOPAY_APP_ID=2553, ZALOPAY_KEY1=KEY1, ZALOPAY_KEY2=KEY2,
                   ZALOPAY_CALLBACK_URL="", ZALOPAY_REDIRECT_URL="")
class ZaloPayTests(Base):
    def new_txn(self):
        g = services.place_order(self.cust, {self.a.pk: 2, self.b.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        with mock.patch.object(zalopay, "_post", side_effect=ok_create):
            payments.start_zalopay(txn, redirect_url="http://x/ret/")
        txn.refresh_from_db()
        return g, txn

    def cb_body(self, txn, amount=None, mac=None, **extra):
        data = {"app_id": 2553, "app_trans_id": txn.app_trans_id, "app_time": 1, "app_user": "u",
                "amount": int(txn.amount) if amount is None else amount, "embed_data": "{}", "item": "[]",
                "zp_trans_id": 230101000001234, "server_time": int(timezone.now().timestamp() * 1000), "channel": 38}
        data.update(extra)
        raw = json.dumps(data)
        return json.dumps({"data": raw, "mac": mac or zalopay.hmac_sha256(KEY2, raw), "type": 1})

    # ------------------------------------------------------------ tạo đơn
    def test_create_request_signature_and_fields(self):
        sent = {}

        def fake(path, fields):
            sent.update(fields)
            return ok_create(path, fields)
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        with mock.patch.object(zalopay, "_post", side_effect=fake):
            url = payments.start_zalopay(txn, redirect_url="http://x/ret/", callback_url="https://pub/cb/")
        self.assertTrue(url.startswith("https://qcgateway.zalopay.vn"))
        txn.refresh_from_db()
        self.assertEqual(txn.provider, "ZALOPAY")
        self.assertEqual(txn.order_url, url)
        self.assertRegex(txn.app_trans_id, r"^\d{6}_TXN[0-9A-F]{16}$")
        self.assertLessEqual(len(txn.app_trans_id), 40)
        self.assertEqual(sent["amount"], int(txn.amount))
        self.assertEqual(sent["callback_url"], "https://pub/cb/")
        self.assertEqual(json.loads(sent["embed_data"]), {"redirecturl": "http://x/ret/"})
        items = json.loads(sent["item"])
        self.assertEqual(sum(i["itemprice"] for i in items), int(txn.amount))
        expect = zalopay.hmac_sha256(KEY1, "|".join(str(sent[k]) for k in
                                     ("app_id", "app_trans_id", "app_user", "amount", "app_time", "embed_data", "item")))
        self.assertEqual(sent["mac"], expect)
        self.assertNotIn("@", sent["app_user"])          # không gửi thông tin cá nhân

    def test_zalopay_rejection_marks_failed_and_allows_retry(self):
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        bad = {"return_code": 2, "sub_return_code": -53, "sub_return_message": "mac sai"}
        with mock.patch.object(zalopay, "_post", return_value=bad):
            with self.assertRaises(payments.PaymentError):
                payments.start_zalopay(txn)
        txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.FAILED)
        self.assertIsNone(txn.processed_at)
        self.assertEqual(payments.create_payment(self.cust, g.pk).status, PaymentTransaction.PENDING)

    def test_network_error_is_wrapped(self):
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        with mock.patch.object(zalopay, "_post", side_effect=zalopay.ZaloPayError("timeout")):
            with self.assertRaises(OrderError):
                payments.start_zalopay(txn)

    def test_pay_group_view_redirects_to_zalopay(self):
        c = Client()
        c.login(username="khach", password="abc12345")
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        with mock.patch.object(zalopay, "_post", side_effect=ok_create):
            r = c.post(reverse("pay_group", args=[g.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://qcgateway.zalopay.vn"))

    # ------------------------------------------------------------ callback
    def test_valid_callback_marks_orders_paid_once(self):
        g, txn = self.new_txn()
        c = Client(enforce_csrf_checks=True)
        r = c.post(reverse("zalopay_callback"), self.cb_body(txn), content_type="application/json")
        self.assertEqual(r.json()["return_code"], 1)
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.PAID})
        txn.refresh_from_db()
        self.assertEqual((txn.status, txn.zp_trans_id), (PaymentTransaction.SUCCESS, 230101000001234))
        self.assertTrue(all(o.payment_txn_id == txn.pk for o in g.orders.all()))
        r = c.post(reverse("zalopay_callback"), self.cb_body(txn), content_type="application/json")
        self.assertEqual(r.json()["return_code"], 2)          # trùng, không cập nhật lại

    def test_callback_bad_mac_amount_or_unknown_rejected(self):
        g, txn = self.new_txn()
        for body in (self.cb_body(txn, mac="0" * 64), self.cb_body(txn, amount=1), self.cb_body(txn, app_trans_id="x_y"),
                     self.cb_body(txn, app_id=1), "không phải json"):
            res = payments.process_zalopay_callback(body)
            self.assertEqual(res["return_code"], -1, body)
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.UNPAID})

    def test_callback_after_cancel_is_late_payment(self):
        g, txn = self.new_txn()
        payments.expire_overdue(g.hold_until + timedelta(seconds=1), reconcile=False)
        res = payments.process_zalopay_callback(self.cb_body(txn, server_time=int((g.hold_until + timedelta(minutes=5)).timestamp() * 1000)))
        self.assertEqual(res["return_code"], 1)
        txn.refresh_from_db()
        self.assertEqual((txn.status, txn.refund_status), (PaymentTransaction.LATE, PaymentTransaction.REFUND_WAIT))

    # ------------------------------------------------------- truy vấn / quay về
    def query_ret(self, code, amount=None, txn=None, server_time=None):
        res = {"return_code": code, "return_message": "m", "amount": amount, "zp_trans_id": 230101000009999,
               "server_time": server_time or int(timezone.now().timestamp() * 1000)}
        return mock.patch.object(zalopay, "_post", return_value=res)

    def test_query_request_mac(self):
        g, txn = self.new_txn()
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 3}) as m:
            payments.sync_zalopay(txn)
        path, fields = m.call_args[0]
        self.assertEqual(path, "/v2/query")
        self.assertEqual(fields["mac"], zalopay.hmac_sha256(KEY1, f"2553|{txn.app_trans_id}|{KEY1}"))

    def test_return_page_confirms_via_query_not_url(self):
        g, txn = self.new_txn()
        c = Client()
        c.login(username="khach", password="abc12345")
        url = reverse("zalopay_return") + f"?apptransid={txn.app_trans_id}&status=1"
        with self.query_ret(3):                                   # URL nói thành công nhưng ZaloPay chưa ghi nhận
            r = c.get(url)
        self.assertRedirects(r, reverse("order_success", args=[g.pk]))
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.UNPAID})
        with self.query_ret(1, amount=int(txn.amount)):
            c.get(url)
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.PAID})
        c.get(reverse("zalopay_return") + "?apptransid=khongco")  # không lỗi 500

    def test_query_failed_then_late_success_goes_to_refund(self):
        g, txn = self.new_txn()
        with self.query_ret(2):
            outcome, _ = payments.sync_zalopay(txn)
        self.assertEqual(outcome, "THAT_BAI")
        txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.FAILED)
        self.assertIsNone(txn.processed_at)
        res = payments.process_zalopay_callback(self.cb_body(txn))     # khách vẫn trả tiền sau đó: không được nuốt tiền
        self.assertEqual(res["return_code"], 1)
        txn.refresh_from_db()
        self.assertEqual((txn.status, txn.refund_status), (PaymentTransaction.LATE, PaymentTransaction.REFUND_WAIT))

    def test_reconcile_before_expiry_saves_paid_orders(self):
        g, txn = self.new_txn()
        paid_ms = int((g.hold_until - timedelta(minutes=1)).timestamp() * 1000)
        with self.query_ret(1, amount=int(txn.amount), server_time=paid_ms):
            n = payments.expire_overdue(g.hold_until + timedelta(minutes=2))
        self.assertEqual(n, 0)
        self.assertEqual(set(g.orders.values_list("status", flat=True)), {Order.PENDING})
        self.assertEqual(set(g.orders.values_list("payment_status", flat=True)), {Order.PAID})

    def test_reconcile_unpaid_still_expires_and_pending_task(self):
        g, txn = self.new_txn()
        with self.query_ret(3):
            self.assertEqual(payments.expire_overdue(g.hold_until + timedelta(minutes=1)), 2)
        self.assertEqual(set(g.orders.values_list("status", flat=True)), {Order.CANCELED})
        g2, t2 = self.new_txn()
        with self.query_ret(1, amount=int(t2.amount)):
            self.assertEqual(payments.reconcile_pending(now=timezone.now() + timedelta(minutes=2)), 1)

    # ------------------------------------------------------------- hoàn tiền
    def paid_and_cancelled(self):
        g, txn = self.new_txn()
        payments.process_zalopay_callback(self.cb_body(txn))
        o = g.orders.first()
        services.cancel_order(o.pk, None, "test")
        return g, txn, Order.objects.get(pk=o.pk)

    def test_refund_order_success(self):
        g, txn, o = self.paid_and_cancelled()
        self.assertEqual(o.payment_status, Order.REFUND_WAIT)
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 1, "sub_return_message": "ok", "refund_id": 77}) as m:
            self.assertEqual(payments.refund_order(o.pk), "DA_HOAN_TIEN")
        path, f = m.call_args[0]
        self.assertEqual(path, "/v2/refund")
        txn.refresh_from_db()
        self.assertEqual((f["zp_trans_id"], f["amount"]), (txn.zp_trans_id, int(o.total)))
        self.assertEqual(f["mac"], zalopay.hmac_sha256(KEY1, f"2553|{f['zp_trans_id']}|{f['amount']}|{f['description']}|{f['timestamp']}"))
        self.assertRegex(f["m_refund_id"], r"^\d{6}_2553_\d{10}$")
        self.assertEqual(Order.objects.get(pk=o.pk).payment_status, Order.REFUNDED)
        rec = RefundRecord.objects.get(order=o)
        self.assertEqual((rec.status, rec.zp_refund_id), (RefundRecord.SUCCESS, 77))
        with self.assertRaises(OrderError):                         # không hoàn hai lần
            payments.refund_order(o.pk)

    def test_refund_processing_then_query_success_no_double_refund(self):
        g, txn, o = self.paid_and_cancelled()
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 3}):
            self.assertEqual(payments.refund_order(o.pk), "DANG_XU_LY")
        self.assertEqual(Order.objects.get(pk=o.pk).payment_status, Order.REFUND_WAIT)
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 1}) as m:
            self.assertEqual(payments.refund_order(o.pk), "DA_HOAN_TIEN")
        self.assertEqual(m.call_args[0][0], "/v2/query_refund")     # hỏi kết quả chứ không gửi hoàn tiền lần 2
        self.assertEqual(RefundRecord.objects.filter(order=o).count(), 1)

    def test_refund_failure_can_retry(self):
        g, txn, o = self.paid_and_cancelled()
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 2, "sub_return_message": "loi"}):
            with self.assertRaises(OrderError):
                payments.refund_order(o.pk)
        self.assertEqual(Order.objects.get(pk=o.pk).payment_status, Order.REFUND_WAIT)
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 1}):
            self.assertEqual(payments.refund_order(o.pk), "DA_HOAN_TIEN")
        self.assertEqual(RefundRecord.objects.filter(order=o).count(), 2)

    def test_refund_late_transaction(self):
        g, txn = self.new_txn()
        payments.expire_overdue(g.hold_until + timedelta(seconds=1), reconcile=False)
        payments.process_zalopay_callback(self.cb_body(txn, server_time=int((g.hold_until + timedelta(minutes=3)).timestamp() * 1000)))
        with mock.patch.object(zalopay, "_post", return_value={"return_code": 1}) as m:
            self.assertEqual(payments.refund_late_transaction(txn.pk), "DA_HOAN_TIEN")
        self.assertEqual(m.call_args[0][1]["amount"], int(txn.amount))
        txn.refresh_from_db()
        self.assertEqual(txn.refund_status, PaymentTransaction.REFUNDED)

    def test_simulated_txn_refund_still_simulated(self):
        g = services.place_order(self.cust, {self.a.pk: 1}, INFO, "CONG_THANH_TOAN")
        txn = payments.create_payment(self.cust, g.pk)
        payments.process_result(payments.build_callback(txn, "success"))
        o = g.orders.first()
        services.cancel_order(o.pk, None, "x")
        with mock.patch.object(zalopay, "_post", side_effect=AssertionError("không được gọi ZaloPay")):
            self.assertEqual(payments.refund_order(o.pk), "DA_HOAN_TIEN")
