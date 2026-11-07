"""Behavior recommendations must include useful collaborative matches."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from .models import BehaviorLog, Category, Product, Shop, Variant
from .services import Actor, recommend


class RecommendationMixTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_collaborative_match_survives_eight_keyword_matches(self):
        user = get_user_model().objects.create_user("buyer", password="password123")
        other = get_user_model().objects.create_user("other", password="password123")
        category = Category.objects.create(slug="electronics", name="Điện tử")
        shop = Shop.objects.create(name="Shop A", status=Shop.ACTIVE)

        def product(name):
            item = Product.objects.create(shop=shop, category=category, name=name)
            Variant.objects.create(product=item, name="Mặc định", price=100000, stock=5)
            return item

        seeds = [product(name) for name in ("Chuột", "Loa", "Bàn phím")]
        related = product("Camera")
        for i in range(8):
            product(f"Tai nghe {i}")
        for seed in seeds:
            BehaviorLog.objects.create(user=user, product=seed, type=BehaviorLog.VIEW)
        BehaviorLog.objects.create(user=other, product=seeds[0], type=BehaviorLog.VIEW)
        BehaviorLog.objects.create(user=other, product=related, type=BehaviorLog.ADD)
        BehaviorLog.objects.create(user=user, type=BehaviorLog.SEARCH, keyword="tai nghe")

        products, personal = recommend(Actor("mine", user), limit=8)
        self.assertTrue(personal)
        self.assertIn(related.pk, [item.pk for item in products])
