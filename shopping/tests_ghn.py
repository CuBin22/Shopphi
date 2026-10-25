import io
import json
import urllib.error
from unittest.mock import patch

from django.test import override_settings, SimpleTestCase
from django.urls import reverse
from django.core.cache import cache

from shopping import services
from shopping.models import Order, OrderGroup
from shopping.tests import Base


@override_settings(GHN_TOKEN="private-test-token", GHN_API_URL="https://dev-online-gateway.ghn.vn", GHN_TIMEOUT=10)
class GHNHTTPTests(SimpleTestCase):
    def test_auth_headers_and_get_parameters(self):
        from shopping import ghn
        with patch("shopping.ghn.urllib.request.urlopen") as call:
            call.return_value.__enter__.return_value = io.BytesIO(b'{"code":200,"data":[]}')
            self.assertEqual(ghn.request("master-data/ward", {"district_id": 2}, shop_id=123, method="GET"), [])
        req = call.call_args.args[0]
        self.assertEqual(req.get_header("Token"), "private-test-token")
        self.assertEqual(req.get_header("Shopid"), "123")
        self.assertTrue(req.full_url.endswith("?district_id=2"))

    def test_shop_error_is_actionable_without_leaking_response(self):
        from shopping import ghn
        body = json.dumps({"code_message": "SHOP_INFO_ERROR", "message": "private-test-token"}).encode()
        error = urllib.error.HTTPError("https://example.invalid", 400, "Bad Request", {}, io.BytesIO(body))
        with patch("shopping.ghn.urllib.request.urlopen", side_effect=error), self.assertRaises(ghn.GHNError) as caught:
            ghn.request("v2/shipping-order/fee", {}, shop_id=123)
        self.assertIn("địa chỉ lấy hàng", str(caught.exception))
        self.assertNotIn("private-test-token", str(caught.exception))
        self.assertFalse(caught.exception.uncertain)


@override_settings(GHN_ENABLED=True, GHN_TOKEN="test-token", GHN_WEBHOOK_SECRET="test-hook")
class GHNTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.s1.ghn_shop_id = 123
        self.s1.save()
        for key, value in {"weight": 500, "length": 20, "width": 10, "height": 5}.items():
            setattr(self.a, key, value)
        self.a.save()
        self.info = {"name": "An", "phone": "0900000000", "address": "12 Nguyen Trai",
                     "province_id": "1", "district_id": "2", "ward_code": "003"}

    def api(self, path, payload=None, shop_id=None, method="POST"):
        if path.endswith("province"):
            return [{"ProvinceID": 1, "ProvinceName": "Tinh A"}]
        if path.endswith("district"):
            return [{"DistrictID": 2, "ProvinceID": 1, "DistrictName": "Huyen B"}]
        if path.endswith("ward"):
            return [{"WardCode": "003", "DistrictID": 2, "WardName": "Xa C"}]
        if path.endswith("/fee"):
            return {"total": 42000}
        if path.endswith("/create"):
            return {"order_code": "GHN123"}
        raise AssertionError(path)

    def place(self, method=OrderGroup.COD):
        with patch("shopping.ghn.request", side_effect=self.api):
            return services.place_order(self.cust, {self.a.pk: 2}, self.info, method).orders.get()

    def test_server_quotes_fee_and_snapshots_package(self):
        order = self.place()
        self.assertEqual(order.shipping_fee, 42000)
        self.assertEqual(order.total, 642000)
        self.assertEqual(order.shipping_data["weight"], 1000)
        self.assertEqual(order.shipping_data["to_ward_code"], "003")

    def test_missing_address_blocks_order_without_stock_change(self):
        self.info["ward_code"] = ""
        with patch("shopping.ghn.request", side_effect=self.api), self.assertRaises(services.OrderError):
            services.place_order(self.cust, {self.a.pk: 2}, self.info, "COD")
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        self.assertFalse(Order.objects.exists())

    def test_confirm_creates_once_and_cod_includes_shipping_once(self):
        order = self.place()
        with patch("shopping.ghn.request", side_effect=self.api) as api:
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        creates = [c for c in api.call_args_list if c.args[0].endswith("/create")]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0].args[1]["cod_amount"], 642000)
        self.assertEqual(creates[0].args[1]["payment_type_id"], 1)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.CONFIRMED)
        self.assertEqual(order.tracking_code, "GHN123")

    def test_unpaid_online_and_wrong_vendor_cannot_create(self):
        order = self.place(OrderGroup.ONLINE)
        with patch("shopping.ghn.request") as api:
            for user in (self.v1u, self.v2u):
                with self.assertRaises(services.OrderError):
                    services.update_status(user, order.pk, Order.CONFIRMED)
            api.assert_not_called()

    def test_definite_first_rejection_allows_cancellation(self):
        from shopping.ghn import GHNError
        order = self.place()
        with patch("shopping.ghn.request", side_effect=GHNError("Invalid phone", uncertain=False)):
            with self.assertRaises(services.OrderError):
                services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        self.assertEqual(services.customer_cancel(self.cust, order.pk, "cancel"), "DA_HUY")

    def test_concurrent_confirmation_does_not_send_request(self):
        from django.db import connection
        order = self.place()
        other = connection.copy(alias="ghn_lock_test")
        try:
            with other.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_lock(%s)", [-order.pk])
            with patch("shopping.ghn.request") as api:
                with self.assertRaises(services.OrderError):
                    services.update_status(self.v1u, order.pk, Order.CONFIRMED)
                api.assert_not_called()
        finally:
            other.close()
        order.refresh_from_db()
        self.assertFalse(order.ghn_creation_pending)

    def test_paid_online_has_zero_cod(self):
        order = self.place(OrderGroup.ONLINE)
        order.payment_status = Order.PAID
        order.save()
        with patch("shopping.ghn.request", side_effect=self.api) as api:
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        self.assertEqual(api.call_args.args[1]["cod_amount"], 0)

    def test_checkout_requires_reviewed_quote_and_preserves_buy_now(self):
        self.client.force_login(self.cust)
        self.client.post(reverse("buy_now"), {"variant": self.a.pk, "qty": 2})
        form = {**self.info, "mua_ngay": "1", "payment_method": "COD", "action": "apply"}
        with patch("shopping.ghn.request", side_effect=self.api):
            response = self.client.post(reverse("checkout"), form)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Tính phí GHN")
            token = response.context["shipping_quote"]
            self.assertTrue(token)
            form["action"] = "place"
            self.client.post(reverse("checkout"), form)
            self.assertFalse(Order.objects.exists())
            form["shipping_quote"] = token
            response = self.client.post(reverse("checkout"), form)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.get().total, 642000)
        self.assertEqual(self.cust.cart_items.count(), 2)

    def test_failed_cancel_keeps_stock_and_success_restores_once(self):
        order = self.place()
        with patch("shopping.ghn.request", side_effect=self.api):
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        detail = {"order_code": "GHN123", "shop_id": 123, "status": "ready_to_pick"}
        with patch("shopping.ghn.request", side_effect=[detail, [{"order_code": "GHN123", "result": False}]]):
            with self.assertRaises(services.OrderError):
                services.vendor_cancel(self.v1u, order.pk, "cancel")
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 8)
        with patch("shopping.ghn.request", side_effect=[detail, [{"order_code": "GHN123", "result": True}]]):
            services.vendor_cancel(self.v1u, order.pk, "cancel")
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        with self.assertRaises(services.OrderError):
            services.vendor_cancel(self.v1u, order.pk, "cancel")

    def test_quote_failure_and_missing_dimensions_do_not_place_order(self):
        from shopping.ghn import GHNError
        with patch("shopping.ghn.request", side_effect=GHNError("offline")), self.assertRaises(services.OrderError):
            services.place_order(self.cust, {self.a.pk: 2}, self.info, "COD")
        self.a.weight = None
        self.a.save()
        with patch("shopping.ghn.request", side_effect=self.api), self.assertRaises(services.OrderError):
            services.place_order(self.cust, {self.a.pk: 2}, self.info, "COD")
        self.assertFalse(Order.objects.exists())
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)

    def test_unknown_creation_then_rejection_still_blocks_cancel(self):
        from shopping.ghn import GHNError
        order = self.place()
        for error in (GHNError("timeout"), GHNError("token rejected", uncertain=False)):
            with patch("shopping.ghn.request", side_effect=error), self.assertRaises(services.OrderError):
                services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        with self.assertRaises(services.OrderError):
            services.customer_cancel(self.cust, order.pk, "cancel")

    def test_completed_local_order_still_updates_carrier_status(self):
        from shopping.shipping import sync_order
        order = self.place()
        order.carrier, order.tracking_code, order.status = "GHN", "GHN123", Order.DONE
        order.save()
        detail = {"order_code": "GHN123", "shop_id": 123, "status": "delivered",
                  "updated_date": "2026-10-25T03:00:00Z"}
        with patch("shopping.ghn.request", return_value=detail):
            sync_order(order.pk)
        order.refresh_from_db()
        self.assertEqual(order.ghn_status, "delivered")
        self.assertEqual(order.status, Order.DONE)

    def test_creation_timeout_blocks_cancel_and_retry_keeps_client_code(self):
        from shopping.ghn import GHNError
        order = self.place()
        with patch("shopping.ghn.request", side_effect=GHNError("timeout")):
            with self.assertRaises(services.OrderError):
                services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        with self.assertRaises(services.OrderError):
            services.customer_cancel(self.cust, order.pk, "cancel")
        with patch("shopping.ghn.request", side_effect=self.api):
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        order.refresh_from_db()
        self.assertFalse(order.ghn_creation_pending)

    def test_callback_requires_secret_and_queries_real_status(self):
        order = self.place()
        with patch("shopping.ghn.request", side_effect=self.api):
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        url = reverse("ghn_webhook")
        payload = {"OrderCode": "GHN123", "Status": "delivered"}
        self.assertEqual(self.client.post(url, payload, content_type="application/json").status_code, 403)
        verified = {"order_code": "GHN123", "shop_id": 123, "status": "picking",
                    "updated_date": "2026-10-25T01:00:00Z"}
        with patch("shopping.ghn.request", return_value=verified):
            response = self.client.post(url, payload, content_type="application/json", HTTP_X_GHN_SECRET="test-hook")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.CONFIRMED)
        self.assertEqual(order.payment_status, Order.UNPAID)

    def test_delivered_is_idempotent_and_stale_event_cannot_regress(self):
        from shopping.shipping import sync_order
        order = self.place()
        with patch("shopping.ghn.request", side_effect=self.api):
            services.update_status(self.v1u, order.pk, Order.CONFIRMED)
        detail = {"order_code": "GHN123", "shop_id": 123, "status": "delivered",
                  "updated_date": "2026-10-25T03:00:00Z"}
        with patch("shopping.ghn.request", return_value=detail):
            sync_order(order.pk)
            sync_order(order.pk)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.DONE)
        self.assertEqual(order.payment_status, Order.PAID)
        self.assertEqual(order.status_logs.filter(new_status=Order.DONE).count(), 1)
        detail.update(status="picked", updated_date="2026-10-25T02:00:00Z")
        with patch("shopping.ghn.request", return_value=detail):
            sync_order(order.pk)
        order.refresh_from_db()
        self.assertEqual(order.ghn_status, "delivered")
