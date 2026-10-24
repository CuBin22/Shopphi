"""Kiểm thử hiển thị tất cả sản phẩm (phân trang) và sao lưu / nạp dữ liệu."""
import json
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import Profile
from catalog.models import Category, Product, Shop, Variant

User = get_user_model()


def make_catalog(n, shop_status=Shop.ACTIVE):
    cat, _ = Category.objects.get_or_create(slug="do-cong-nghe", defaults={"name": "Đồ công nghệ"})
    owner = User.objects.create_user(username=f"ban{User.objects.count()}", password="x")
    Profile.objects.create(user=owner, role=Profile.VENDOR)
    shop = Shop.objects.create(name=f"Shop {Shop.objects.count()}", status=shop_status, owner=owner)
    for i in range(n):
        p = Product.objects.create(shop=shop, category=cat, name=f"Sản phẩm số {i:03d}", tags="thử")
        Variant.objects.create(product=p, name="Mặc định", price=10000 + i, stock=5)
    return shop


class AllProductsTests(TestCase):
    def test_search_shows_every_product_across_pages(self):
        make_catalog(70)                                     # nhiều hơn mức cắt cứng 60 trước đây
        seen = set()
        r = self.client.get(reverse("search"))
        self.assertContains(r, "70 sản phẩm")
        self.assertEqual(r.context["page"].paginator.num_pages, 3)
        for n in (1, 2, 3):
            r = self.client.get(reverse("search"), {"trang": n})
            seen |= {p.pk for p in r.context["results"]}
        self.assertEqual(len(seen), 70)

    def test_page_links_keep_filters_and_do_not_log_new_search(self):
        make_catalog(30)
        from catalog.models import BehaviorLog
        r = self.client.get(reverse("search"), {"q": "san pham", "sap_xep": "gia-tang"})
        before = BehaviorLog.objects.filter(type="SEARCH").count()
        self.assertContains(r, "sap_xep=gia-tang")
        self.assertContains(r, "trang=2")
        self.client.get(reverse("search"), {"q": "san pham", "sap_xep": "gia-tang", "loc": "1", "trang": 2})
        self.assertEqual(BehaviorLog.objects.filter(type="SEARCH").count(), before)

    def test_bad_page_number_falls_back(self):
        make_catalog(30)
        for bad in ("abc", "999", "-1", "0"):
            self.assertEqual(self.client.get(reverse("search"), {"trang": bad}).status_code, 200)

    def test_hidden_and_locked_shop_products_not_listed(self):
        make_catalog(3)
        make_catalog(5, shop_status=Shop.LOCKED)
        hidden = Product.objects.filter(shop__status=Shop.ACTIVE).first()
        hidden.status = Product.HIDDEN
        hidden.save()
        r = self.client.get(reverse("search"))
        self.assertEqual(r.context["total"], 2)

    def test_home_has_all_products_section(self):
        make_catalog(20)
        r = self.client.get(reverse("home"))
        self.assertContains(r, "Tất cả sản phẩm")
        self.assertContains(r, "Xem tất cả 20 sản phẩm")
        self.assertEqual(len(r.context["all_products"]), 12)

    def test_empty_catalog(self):
        r = self.client.get(reverse("search"))
        self.assertContains(r, "Không tìm thấy")


class BackupRestoreTests(TransactionTestCase):
    def counts(self):
        return (User.objects.count(), Product.objects.count(), Variant.objects.count(), Shop.objects.count())

    def setUp(self):
        make_catalog(7)
        self.tmp = Path(tempfile.mkdtemp()) / "sao_luu.json"

    def test_export_then_import_restores_everything(self):
        before = self.counts()
        names = sorted(Product.objects.values_list("name", flat=True))
        call_command("export_data", out=str(self.tmp), stdout=StringIO())
        text = self.tmp.read_text(encoding="utf-8")
        self.assertIn("Sản phẩm số 000", text)                # tiếng Việt giữ nguyên, không bị escape
        data = json.loads(text)
        models = {row["model"] for row in data}
        self.assertNotIn("sessions.session", models)
        self.assertNotIn("contenttypes.contenttype", models)
        Product.objects.all().delete()
        Shop.objects.all().delete()
        self.assertNotEqual(self.counts(), before)
        call_command("import_data", str(self.tmp), stdout=StringIO())
        self.assertEqual(self.counts(), before)
        self.assertEqual(sorted(Product.objects.values_list("name", flat=True)), names)
        # sản phẩm nạp lại vẫn hiển thị trên trang
        self.assertEqual(self.client.get(reverse("search")).context["total"], 7)

    def test_import_with_flush_replaces_data(self):
        call_command("export_data", out=str(self.tmp), stdout=StringIO())
        make_catalog(4)                                       # dữ liệu "thừa" sẽ bị xóa khi --flush
        call_command("import_data", str(self.tmp), flush=True, yes=True, stdout=StringIO())
        self.assertEqual(Product.objects.count(), 7)
        self.assertEqual(Shop.objects.count(), 1)

    def test_no_logs_option(self):
        from catalog.models import BehaviorLog
        BehaviorLog.objects.create(session_key="s", type="VIEW")
        call_command("export_data", out=str(self.tmp), no_logs=True, stdout=StringIO())
        self.assertNotIn("catalog.behaviorlog", {r["model"] for r in json.loads(self.tmp.read_text(encoding="utf-8"))})

    def test_import_errors(self):
        with self.assertRaises(CommandError):
            call_command("import_data", "khong_co.json", stdout=StringIO())
        bad = self.tmp.with_suffix(".txt")
        bad.write_text("[]")
        with self.assertRaises(CommandError):
            call_command("import_data", str(bad), stdout=StringIO())
        broken = self.tmp.with_name("hong.json")
        broken.write_text('[{"model": "catalog.product", "pk": 1, "fields": {"name": "x"}}]', encoding="utf-8")
        before = self.counts()
        with self.assertRaises(Exception):
            call_command("import_data", str(broken), stdout=StringIO())
        self.assertEqual(self.counts(), before)              # file lỗi: không thay đổi gì

    def test_check_db(self):
        out = StringIO()
        call_command("check_db", stdout=out)
        self.assertIn("Kết nối OK", out.getvalue())
        self.assertIn("catalog.Product", out.getvalue())
