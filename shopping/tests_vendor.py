"""Kiểm thử module Người bán: ảnh sản phẩm, kho nhanh, mã giảm giá, đơn hàng/phiếu giao vận, đánh giá, thông tin gian hàng."""
import os
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from catalog.models import Product, ProductImage, Shop, Variant
from shopping import services
from shopping.models import Coupon, Order, Review

from .tests import Base, mk_user

TMP_MEDIA = tempfile.mkdtemp(prefix="shopphi_media_")


def png(size=(400, 300), color=(200, 30, 30), mode="RGB", fmt="PNG"):
    buf = BytesIO()
    Image.new(mode, size, color).save(buf, fmt)
    return buf.getvalue()


def upload(name="a.png", data=None, ctype="image/png"):
    return SimpleUploadedFile(name, data if data is not None else png(), content_type=ctype)


def media_files():
    root = os.path.join(TMP_MEDIA, "products")
    return set(os.listdir(root)) if os.path.isdir(root) else set()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class VendorBase(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.c = Client()
        self.c.login(username="ban1", password="abc12345")

    def form(self, **kw):
        d = {"category": self.cat.pk, "name": "Loa mini", "brand": "X", "tags": "loa", "description": "d", "specs": "",
             "status": Product.VISIBLE, "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "0", "variants-MIN_NUM_FORMS": "0",
             "variants-MAX_NUM_FORMS": "1000", "variants-0-name": "Đen", "variants-0-price": "450000", "variants-0-stock": "7"}
        d.update(kw)
        return d


class ProductImageTests(VendorBase):
    def test_upload_cover_and_gallery_are_normalized_jpeg(self):
        big = png(size=(3000, 2000))
        r = self.c.post(reverse("product_add"), self.form(image=upload("big.png", big),
                        gallery=[upload("g1.png"), upload("g2.png", png(color=(0, 0, 200)))]))
        self.assertRedirects(r, reverse("product_list"))
        p = Product.objects.get(name="Loa mini")
        self.assertTrue(p.image.name.endswith(".jpg"))
        self.assertEqual(p.extra_images.count(), 2)
        with Image.open(p.image.path) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 1200)             # đã thu nhỏ
        self.assertEqual(len(p.gallery()), 3)

    def test_rejects_non_image_disguised_as_png(self):
        r = self.c.post(reverse("product_add"), self.form(image=upload("x.png", b"<?php evil ?>")))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Loa mini").exists())

    def test_rejects_svg_gif_and_oversize_and_tiny(self):
        for name, data, ctype in (("a.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
                                  ("a.gif", png(fmt="GIF"), "image/gif"), ("tiny.png", png(size=(50, 50)), "image/png")):
            r = self.c.post(reverse("product_add"), self.form(gallery=[upload(name, data, ctype)]))
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, name)
        with override_settings(PRODUCT_IMAGE_MAX_BYTES=1000):
            r = self.c.post(reverse("product_add"), self.form(gallery=[upload("big.png", png(size=(900, 900)))]))
            self.assertContains(r, "dung lượng vượt")
        self.assertFalse(Product.objects.filter(name="Loa mini").exists())

    def test_png_with_transparency_flattened(self):
        self.c.post(reverse("product_add"), self.form(image=upload("t.png", png(mode="RGBA", color=(0, 0, 0, 0)))))
        with Image.open(Product.objects.get(name="Loa mini").image.path) as im:
            self.assertEqual(im.mode, "RGB")
            self.assertEqual(im.getpixel((5, 5)), (255, 255, 255))

    def test_max_image_count_enforced(self):
        files = [upload(f"g{i}.png") for i in range(7)]
        r = self.c.post(reverse("product_add"), self.form(image=upload(), gallery=files))
        self.assertContains(r, "tối đa 6 ảnh")
        self.assertFalse(Product.objects.filter(name="Loa mini").exists())

    def test_delete_extra_and_swap_cover_and_file_cleanup(self):
        self.c.post(reverse("product_add"), self.form(image=upload("c.png"), gallery=[upload("g1.png", png(color=(1, 2, 3))), upload("g2.png", png(color=(9, 9, 9)))]))
        p = Product.objects.get(name="Loa mini")
        e1, e2 = list(p.extra_images.all())
        old_cover, n1, n2 = p.image.name, e1.image.name, e2.image.name
        edit = lambda **kw: self.c.post(reverse("product_edit", args=[p.pk]), self.form(**{
            "variants-TOTAL_FORMS": "1", "variants-INITIAL_FORMS": "1", "variants-0-id": p.variants.first().pk,
            "variants-0-product": p.pk, **kw}))
        with self.captureOnCommitCallbacks(execute=True):
            edit(cover_from=e1.pk, del_img=[e2.pk])
        p.refresh_from_db()
        self.assertEqual(p.image.name, n1)                           # ảnh phụ 1 thành ảnh bìa
        self.assertEqual(list(p.extra_images.values_list("image", flat=True)), [old_cover])   # ảnh bìa cũ thành ảnh phụ
        self.assertFalse(os.path.exists(os.path.join(TMP_MEDIA, n2)))  # ảnh đã xóa bị dọn khỏi đĩa
        self.assertTrue(os.path.exists(os.path.join(TMP_MEDIA, old_cover)))
        with self.captureOnCommitCallbacks(execute=True):
            edit(image=upload("new.png", png(color=(5, 5, 5))))       # thay ảnh bìa: file bìa cũ (n1) bị dọn
        p.refresh_from_db()
        self.assertNotEqual(p.image.name, n1)
        self.assertFalse(os.path.exists(os.path.join(TMP_MEDIA, n1)))

    def test_cannot_touch_images_of_other_shop(self):
        other = Product.objects.get(pk=self.p2.pk)
        pi = ProductImage.objects.create(product=other, image=upload().name and "products/x.jpg")
        r = self.c.post(reverse("product_edit", args=[other.pk]), self.form())
        self.assertEqual(r.status_code, 404)
        # id ảnh của sản phẩm khác truyền vào form sản phẩm mình: bị bỏ qua
        self.c.post(reverse("product_edit", args=[self.p1.pk]), self.form(**{
            "variants-INITIAL_FORMS": "1", "variants-0-id": self.a.pk, "variants-0-product": self.p1.pk, "del_img": [pi.pk]}))
        self.assertTrue(ProductImage.objects.filter(pk=pi.pk).exists())

    def test_deleting_product_removes_files(self):
        self.c.post(reverse("product_add"), self.form(image=upload(), gallery=[upload("g.png")]))
        p = Product.objects.get(name="Loa mini")
        files = [p.image.name] + [e.image.name for e in p.extra_images.all()]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(services.delete_product(self.v1u, p.pk), "DA_XOA")
        for f in files:
            self.assertFalse(os.path.exists(os.path.join(TMP_MEDIA, f)))

    def test_images_displayed_on_pages(self):
        self.c.post(reverse("product_add"), self.form(image=upload(), gallery=[upload("g.png")]))
        p = Product.objects.get(name="Loa mini")
        page = Client().get(p.get_absolute_url())
        self.assertContains(page, p.image.url)
        self.assertContains(page, "gallery__thumb")                   # có thư viện ảnh khi > 1 ảnh
        self.assertContains(Client().get(reverse("search")), p.image.url)
        self.assertContains(self.c.get(reverse("product_list")), p.image.url)
        self.assertTrue(os.path.exists(p.image.path))                # file thật nằm trong MEDIA_ROOT

    def test_single_image_has_no_thumb_strip_and_no_image_has_placeholder(self):
        page = Client().get(self.p1.get_absolute_url())
        self.assertNotContains(page, "gallery__thumb")
        self.assertContains(page, "svg")                              # glyph thay thế



class InventoryTests(VendorBase):
    def post(self, rows, **q):
        data = {"ids": [v.pk for v, *_ in rows]}
        for v, price, stock, orig in rows:
            data.update({f"price_{v.pk}": price, f"stock_{v.pk}": stock, f"orig_stock_{v.pk}": orig})
        return self.c.post(reverse("inventory"), data)

    def test_bulk_update_price_and_stock(self):
        self.post([(self.a, 310000, 20, 10)])
        self.a.refresh_from_db()
        self.assertEqual((int(self.a.price), self.a.stock), (310000, 20))

    def test_stock_applied_as_delta_when_orders_came_in_meanwhile(self):
        Variant.objects.filter(pk=self.a.pk).update(stock=7)          # khách vừa mua 3 trong lúc người bán đang sửa
        self.post([(self.a, 300000, 15, 10)])                        # người bán tăng thêm 5 so với số cũ (10)
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 12)

    def test_invalid_rows_reject_everything(self):
        r = self.post([(self.a, 0, 5, 10)], )
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 10)
        r = self.c.get(reverse("inventory"))
        self.assertContains(r, "giá bán phải lớn hơn 0")
        Variant.objects.filter(pk=self.a.pk).update(stock=2)
        self.post([(self.a, 300000, 5, 10)])                         # -5 so với số cũ nhưng chỉ còn 2 -> âm
        self.a.refresh_from_db()
        self.assertEqual(self.a.stock, 2)

    def test_cannot_edit_other_shop_variants_and_filters(self):
        self.post([(self.b, 1, 99, 5)])
        self.b.refresh_from_db()
        self.assertEqual(self.b.stock, 5)
        Variant.objects.filter(pk=self.a.pk).update(stock=0)
        r = self.c.get(reverse("inventory"), {"loc": "het"})
        self.assertContains(r, "Tai nghe A")
        self.assertNotContains(r, "Sạc B")
        self.assertContains(self.c.get(reverse("inventory"), {"loc": "sap_het"}), "Không có biến thể")


class ProductListTests(VendorBase):
    def test_filters_and_pagination(self):
        for i in range(25):
            p = Product.objects.create(shop=self.s1, category=self.cat, name=f"SP {i:02d}")
            Variant.objects.create(product=p, name="m", price=1000, stock=0 if i < 3 else 50)
        r = self.c.get(reverse("product_list"))
        self.assertEqual(r.context["page"].paginator.count, 26)
        self.assertEqual(len(r.context["products"]), 20)
        self.assertEqual(self.c.get(reverse("product_list"), {"ton_kho": "het_hang"}).context["page"].paginator.count, 3)
        self.assertEqual(self.c.get(reverse("product_list"), {"q": "SP 1"}).context["page"].paginator.count, 10)
        self.assertEqual(self.c.get(reverse("product_list"), {"ton_kho": "sap_het"}).context["page"].paginator.count, 0)
        for bad in ("abc", "99"):
            self.assertEqual(self.c.get(reverse("product_list"), {"trang": bad}).status_code, 200)

    def test_empty_variant_template_present_for_js(self):
        r = self.c.get(reverse("product_add"))
        self.assertContains(r, "variants-__prefix__-name")
        self.assertContains(r, "add-variant")


class CouponLifecycleTests(VendorBase):
    def data(self, c, **kw):
        d = {"code": c.code, "kind": c.kind, "value": c.value, "max_discount": "", "min_order": c.min_order,
             "starts": c.starts.strftime("%Y-%m-%dT%H:%M"), "expires": c.expires.strftime("%Y-%m-%dT%H:%M"), "max_uses": c.max_uses}
        d.update(kw)
        return d

    def test_edit_unused_coupon_fully(self):
        r = self.c.post(reverse("coupon_edit", args=[self.sc.pk]), self.data(self.sc, value=30000, code="shop1x"))
        self.assertRedirects(r, reverse("coupon_detail", args=[self.sc.pk]))
        self.sc.refresh_from_db()
        self.assertEqual((self.sc.value, self.sc.code), (30000, "SHOP1X"))

    def test_used_coupon_only_extend_expiry_and_uses(self):
        self.order(shop_coupon_code="SHOP1") if False else None
        Coupon.objects.filter(pk=self.sc.pk).update(used_count=2)
        self.sc.refresh_from_db()
        new_exp = (self.sc.expires + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M")
        self.c.post(reverse("coupon_edit", args=[self.sc.pk]), self.data(self.sc, value=99999, code="HACK", expires=new_exp, max_uses=10))
        self.sc.refresh_from_db()
        self.assertEqual((self.sc.value, self.sc.code, self.sc.max_uses), (20000, "SHOP1", 10))     # giá trị/mã không đổi
        r = self.c.post(reverse("coupon_edit", args=[self.sc.pk]), self.data(self.sc, max_uses=1))
        self.assertContains(r, "không được nhỏ hơn")

    def test_toggle_blocks_new_orders(self):
        self.c.post(reverse("coupon_toggle", args=[self.sc.pk]))
        self.sc.refresh_from_db()
        self.assertFalse(self.sc.is_active)
        with self.assertRaises(services.OrderError):
            services.validate_coupon("SHOP1", Coupon.SHOP, 500000, shop=self.s1)
        self.c.post(reverse("coupon_toggle", args=[self.sc.pk]))
        self.assertTrue(services.validate_coupon("SHOP1", Coupon.SHOP, 500000, shop=self.s1))

    def test_delete_rules(self):
        self.c.post(reverse("coupon_delete", args=[self.sc.pk]))
        self.assertFalse(Coupon.objects.filter(pk=self.sc.pk).exists())
        now = timezone.now()
        used = Coupon.objects.create(code="DADUNG", scope="GIAN_HANG", shop=self.s1, kind="SO_TIEN", value=1000,
                                     starts=now, expires=now + timedelta(days=1), max_uses=3)
        Coupon.objects.filter(pk=used.pk).update(used_count=1)
        self.c.post(reverse("coupon_delete", args=[used.pk]))
        self.assertTrue(Coupon.objects.filter(pk=used.pk).exists())

    def test_vendor_cannot_manage_others_or_global(self):
        for url in ("coupon_edit", "coupon_toggle", "coupon_delete"):
            self.assertEqual(self.c.post(reverse(url, args=[self.gc.pk])).status_code, 404)
        other = Client()
        other.login(username="ban2", password="abc12345")
        self.assertEqual(other.post(reverse("coupon_delete", args=[self.sc.pk])).status_code, 404)
        self.assertTrue(Coupon.objects.filter(pk=self.sc.pk).exists())

    def test_admin_manages_global_only(self):
        a = Client()
        a.login(username="adm", password="abc12345")
        a.post(reverse("coupon_toggle", args=[self.gc.pk]))
        self.gc.refresh_from_db()
        self.assertFalse(self.gc.is_active)
        self.assertEqual(a.post(reverse("coupon_toggle", args=[self.sc.pk])).status_code, 404)


class VendorOrderTests(VendorBase):
    def test_filters_and_pagination(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        self.assertContains(self.c.get(reverse("vendor_orders"), {"q": str(o.pk)}), f"Đơn #{o.pk}")
        self.assertContains(self.c.get(reverse("vendor_orders"), {"q": "0900000000"}), f"Đơn #{o.pk}")
        self.assertNotContains(self.c.get(reverse("vendor_orders"), {"q": "khongco"}), f"Đơn #{o.pk}")
        self.assertNotContains(self.c.get(reverse("vendor_orders"), {"thanh_toan": "DA_THANH_TOAN"}), f"Đơn #{o.pk}")
        self.assertContains(self.c.get(reverse("vendor_orders"), {"tu_ngay": "2000-01-01", "den_ngay": "2999-01-01"}), f"Đơn #{o.pk}")
        self.assertEqual(self.c.get(reverse("vendor_orders"), {"tu_ngay": "hỏng", "trang": "x"}).status_code, 200)
        self.assertNotContains(self.c.get(reverse("vendor_orders")), f"Đơn #{g.orders.get(shop=self.s2).pk} ")

    def test_packing_slip_rules(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        r = self.c.get(reverse("packing_slip", args=[o.pk]))
        self.assertRedirects(r, reverse("vendor_order_detail", args=[o.pk]))      # chưa xác nhận: chưa có phiếu
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        r = self.c.get(reverse("packing_slip", args=[o.pk]))
        self.assertContains(r, "PHIẾU GIAO VẬN")
        self.assertContains(r, "Thu hộ (COD)")
        self.assertContains(r, "HCM")
        other = Client()
        other.login(username="ban2", password="abc12345")
        self.assertEqual(other.get(reverse("packing_slip", args=[o.pk])).status_code, 404)

    def test_order_detail_shows_thumbnails_link(self):
        g = self.order()
        o = g.orders.get(shop=self.s1)
        services.update_status(self.v1u, o.pk, Order.CONFIRMED)
        self.assertContains(self.c.get(reverse("vendor_order_detail", args=[o.pk])), reverse("packing_slip", args=[o.pk]))


class VendorMiscTests(VendorBase):
    def test_reviews_page_scoped_to_own_shop(self):
        cust2 = mk_user("khach2", "KHACH_HANG")
        Review.objects.create(user=self.cust, product=self.p1, rating=5, comment="Rất tốt")
        Review.objects.create(user=cust2, product=self.p1, rating=2, comment="Tạm")
        Review.objects.create(user=self.cust, product=self.p2, rating=1, comment="Của shop khác")
        r = self.c.get(reverse("vendor_reviews"))
        self.assertEqual(r.context["total"], 2)
        self.assertNotContains(r, "Của shop khác")
        self.assertEqual(len(self.c.get(reverse("vendor_reviews"), {"sao": "5"}).context["reviews"]), 1)
        self.assertEqual(self.c.get(reverse("vendor_reviews"), {"sao": "x", "san_pham": "y"}).status_code, 200)
        self.assertEqual(Client().get(reverse("vendor_reviews")).status_code, 302)

    def test_customer_cannot_open_vendor_pages(self):
        c = Client()
        c.login(username="khach", password="abc12345")
        for name in ("inventory", "vendor_reviews", "shop_info"):
            self.assertNotEqual(c.get(reverse(name)).status_code, 200, name)

    def test_shop_info_edit_keeps_name_and_type(self):
        r = self.c.post(reverse("shop_info"), {"description": "Mô tả mới", "pickup_address": "Q1", "contact": "0911111111", "name": "HACK"})
        self.assertRedirects(r, reverse("manage_home"))
        self.s1.refresh_from_db()
        self.assertEqual((self.s1.name, self.s1.description, self.s1.pickup_address), ("S1", "Mô tả mới", "Q1"))
        self.assertContains(self.c.post(reverse("shop_info"), {"description": "", "pickup_address": "", "contact": ""}), "required")

    def test_dashboard_kpis(self):
        Variant.objects.filter(pk=self.a.pk).update(stock=0)
        r = self.c.get(reverse("manage_home"))
        self.assertEqual(r.context["n_out"], 1)
        self.assertContains(r, "hết hàng")
        self.assertContains(r, reverse("inventory"))
