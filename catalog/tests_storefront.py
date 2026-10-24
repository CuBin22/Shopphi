from django.test import TestCase
from django.urls import reverse

from .models import Product, Shop
from .tests import make_catalog


class StorefrontTests(TestCase):
    def test_banners_only_link_to_available_products_with_images(self):
        make_catalog(8)
        products = list(Product.objects.all())
        for product in products:
            Product.objects.filter(pk=product.pk).update(image=f"products/real-{product.pk}.jpg")
        Product.objects.filter(pk=products[0].pk).update(status=Product.HIDDEN)
        products[1].variants.update(stock=0)
        Product.objects.filter(pk=products[2].pk).update(image="")
        locked = make_catalog(1, shop_status=Shop.LOCKED)
        locked.products.update(image="products/locked.jpg")
        response = self.client.get(reverse("home"))
        banners = response.context["banner_products"]
        self.assertEqual(len(banners), 5)
        self.assertEqual({p.pk for p in banners}, {p.pk for p in products[3:]})
        for product in banners:
            self.assertContains(response, product.image.url)
            self.assertContains(response, product.get_absolute_url())

    def test_empty_catalog_has_search_and_no_carousel_controls(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="q-compact"')
        self.assertContains(response, "Khám phá gian hàng")
        self.assertNotContains(response, 'data-carousel-next')

    def test_single_banner_does_not_offer_rotation(self):
        make_catalog(1)
        Product.objects.update(image="products/real.jpg")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "products/real.jpg")
        self.assertNotContains(response, 'data-carousel-next')
