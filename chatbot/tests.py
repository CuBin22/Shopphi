"""Regression checks for chat input, retrieval and safe fallbacks."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product, Shop, Variant
from catalog.services import Actor
from shopping.models import Order, OrderGroup

from . import embeddings, service
from .models import ChatLog, ProductEmbedding
from .service import ChatError


class ChatbotRegressionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("buyer", password="password123")
        self.category = Category.objects.create(slug="electronics", name="Điện tử")
        self.shop = Shop.objects.create(name="Shop A", status=Shop.ACTIVE)

    def product(self, name, price, stock=5):
        product = Product.objects.create(shop=self.shop, category=self.category, name=name)
        Variant.objects.create(product=product, name="Mặc định", price=price, stock=stock)
        return product

    def test_json_array_is_rejected_instead_of_server_error(self):
        response = self.client.post(reverse("chatbot"), data="[]", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_message_must_be_text(self):
        response = self.client.post(reverse("chatbot"), data='{"message": ["tai nghe"]}',
                                    content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_guest_chat_reserves_slot_and_returns_history(self):
        response = self.client.post(reverse("chatbot"), data='{"message": "xin chào"}',
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatLog.objects.count(), 1)
        self.assertEqual(len(self.client.get(reverse("chatbot_history")).json()["messages"]), 1)

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_budget_range_excludes_product_above_upper_bound(self):
        wanted = self.product("Tai nghe 750", 750000)
        self.product("Tai nghe 1200", 1200000)
        result = service.retrieve("Gợi ý tai nghe từ 500 nghìn đến 1 triệu")
        self.assertEqual([p.pk for p in result], [wanted.pk])

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_other_product_question_does_not_prepend_current_product(self):
        current = self.product("Loa bluetooth", 700000)
        wanted = self.product("Tai nghe gaming", 800000)
        result = service.retrieve("Gợi ý tai nghe gaming", current_id=current.pk)
        self.assertEqual([p.pk for p in result], [wanted.pk])

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"})
    @mock.patch("chatbot.embeddings.embed_texts", side_effect=OSError("provider down"))
    def test_changed_product_does_not_use_old_embedding(self, _embedding):
        product = self.product("Tai nghe mới", 750000)
        ProductEmbedding.objects.create(product=product, vector=[1.0, 0.0],
                                        content_hash="old content", model="gemini-embedding-001:768")
        self.assertEqual(embeddings.refresh_product_embeddings([product]), {})

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"})
    @mock.patch("chatbot.service.call_llm", return_value="")
    def test_empty_model_reply_for_order_uses_database_fallback(self, _llm):
        group = OrderGroup.objects.create(user=self.user, recipient_name="Buyer",
                                          recipient_phone="0900000000", address="HCM")
        order = Order.objects.create(group=group, shop=self.shop, subtotal=100000, total=100000)
        response = service.ask(Actor("session", self.user), "Đơn hàng của tôi")
        self.assertEqual(response["status"], ChatLog.OK)
        self.assertIn(f"#{order.pk}", response["answer"])

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": "key"})
    @mock.patch("chatbot.service.embed_text", return_value=[])
    @mock.patch("chatbot.service.refresh_product_embeddings", return_value={})
    def test_question_reserves_rate_slot_before_external_model_call(self, _refresh, _embed):
        self.product("Tai nghe A", 750000)
        actor = Actor("session", self.user)

        def external_answer(question, contexts, intent):
            self.assertEqual(ChatLog.objects.filter(user=self.user).count(), 1)
            return "Tai nghe A"

        with mock.patch("chatbot.service.call_llm", side_effect=external_answer):
            self.assertEqual(service.ask(actor, "Giá Tai nghe A")["status"], ChatLog.OK)

    @mock.patch.dict("os.environ", {"GEMINI_API_KEY": ""})
    def test_ninth_message_is_rejected_without_new_log(self):
        actor = Actor("session", self.user)
        for _ in range(service.MAX_PER_MINUTE):
            service.ask(actor, "Xin chào")
        with self.assertRaises(ChatError):
            service.ask(actor, "Xin chào")
        self.assertEqual(ChatLog.objects.filter(user=self.user).count(), service.MAX_PER_MINUTE)
