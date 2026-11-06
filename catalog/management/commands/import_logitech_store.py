"""Create a demo Logitech shop and import the product photos supplied in Logitech/."""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Profile
from catalog.images import process_image
from catalog.models import Category, Product, ProductImage, Shop, Variant


ROOT = Path(__file__).resolve().parents[3] / "Logitech"
OWNER_EMAIL = "logitech@shopphi.vn"
OWNER_PASSWORD = "Logitech@12345"
ITEMS = [
    {
        "folder": "Chuột có dây Logitech M90 - Siêu bền, siêu tiết kiệm, nhỏ gọn, thiết kế ôm tay",
        "name": "Chuột có dây Logitech M90",
        "price": 79000,
        "desc": "Chuột quang Logitech M90 thiết kế gọn nhẹ, cắm USB là dùng, phù hợp học tập và công việc văn phòng hằng ngày. Dáng chuột đối xứng, dễ làm quen; sản phẩm có dây giúp kết nối ổn định, không cần pin.",
        "specs": "Thương hiệu: Logitech\nModel: M90\nKết nối: USB có dây\nCảm biến: Quang học\nThiết kế: Đối xứng, nhỏ gọn\nKhối lượng đóng gói: 250 g\nKích thước đóng gói (D × R × C): 14 × 9 × 5 cm",
        "dims": (250, 14, 9, 5),
    },
    {
        "folder": "Chuột gaming có dây Logitech G203 Lightsync - Tùy chỉnh RGB, 6 nút lập trình, nhẹ",
        "name": "Chuột gaming Logitech G203 LIGHTSYNC",
        "price": 499000,
        "desc": "Chuột gaming có dây Logitech G203 LIGHTSYNC với đèn RGB tùy chỉnh và 6 nút điều khiển. Thiết kế nhỏ gọn, phù hợp chơi game và sử dụng máy tính hằng ngày. Kết nối USB có dây, không cần pin.",
        "specs": "Thương hiệu: Logitech G\nModel: G203 LIGHTSYNC\nKết nối: USB có dây\nNút: 6 nút lập trình\nĐèn: RGB LIGHTSYNC tùy chỉnh\nKhối lượng đóng gói: 350 g\nKích thước đóng gói (D × R × C): 15 × 10 × 6 cm",
        "dims": (350, 15, 10, 6),
    },
    {
        "folder": "Chuột gaming không dây Logitech G G305 LIGHTSPEED - Hero 12K DPI, Nhẹ 99g, 6 nút lập trình, Pin 250h",
        "name": "Chuột gaming không dây Logitech G G305 LIGHTSPEED",
        "price": 1099000,
        "desc": "Chuột gaming Logitech G G305 sử dụng kết nối không dây LIGHTSPEED và cảm biến HERO. Thiết kế gọn nhẹ, 6 nút lập trình, dùng pin AA; phù hợp chơi game và mang theo khi di chuyển.",
        "specs": "Thương hiệu: Logitech G\nModel: G305 LIGHTSPEED\nKết nối: LIGHTSPEED 2.4 GHz\nCảm biến: HERO, tối đa 12.000 DPI\nNút: 6 nút lập trình\nNguồn: 1 pin AA\nKhối lượng đóng gói: 350 g\nKích thước đóng gói (D × R × C): 15 × 10 × 6 cm",
        "dims": (350, 15, 10, 6),
    },
    {
        "folder": "Chuột Gaming không dây Logitech G PRO X SUPERLIGHT 2c - Chuẩn Pro-Grade, Nhẹ 51g, sạc USB-C, cảm biến 44K DPI",
        "name": "Chuột gaming Logitech G PRO X SUPERLIGHT 2c",
        "price": 3490000,
        "desc": "Chuột gaming không dây Logitech G PRO X SUPERLIGHT 2c hướng đến thi đấu chuyên nghiệp, thân chuột siêu nhẹ theo thông tin sản phẩm. Trang bị cảm biến HERO 2 độ phân giải cao, kết nối LIGHTSPEED và sạc USB-C.",
        "specs": "Thương hiệu: Logitech G\nModel: PRO X SUPERLIGHT 2c\nKết nối: LIGHTSPEED không dây\nCảm biến: HERO 2, tối đa 44.000 DPI\nKhối lượng chuột: khoảng 51 g (theo tên sản phẩm)\nSạc: USB-C\nKhối lượng đóng gói: 400 g\nKích thước đóng gói (D × R × C): 16 × 11 × 7 cm",
        "dims": (400, 16, 11, 7),
    },
    {
        "folder": "Chuột Gaming không dây Logitech G Pro X2 SUPERSTRIKE LIGHTSPEED - Siêu nhẹ 61g, hiệu suất nhanh, USB-C",
        "name": "Chuột gaming không dây Logitech G PRO X2 SUPERSTRIKE LIGHTSPEED",
        "price": 4990000,
        "desc": "Chuột gaming Logitech G PRO X2 SUPERSTRIKE LIGHTSPEED dành cho trải nghiệm chơi game tốc độ cao. Thiết kế không dây LIGHTSPEED, thân chuột nhẹ theo thông tin sản phẩm và sạc USB-C. Thông số chi tiết được ghi theo thông tin trong tên thư mục ảnh.",
        "specs": "Thương hiệu: Logitech G\nModel: PRO X2 SUPERSTRIKE LIGHTSPEED\nKết nối: LIGHTSPEED không dây\nKhối lượng chuột: khoảng 61 g (theo tên sản phẩm)\nSạc: USB-C\nKhối lượng đóng gói: 450 g\nKích thước đóng gói (D × R × C): 17 × 12 × 7 cm",
        "dims": (450, 17, 12, 7),
    },
]


class Command(BaseCommand):
    help = "Import Logitech Store demo shop and its supplied product images."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        owner, created = User.objects.get_or_create(
            username=OWNER_EMAIL,
            defaults={"email": OWNER_EMAIL, "first_name": "Chủ Logitech Store"},
        )
        if created:
            owner.set_password(OWNER_PASSWORD)
            owner.save(update_fields=["password"])
        Profile.objects.update_or_create(user=owner, defaults={"role": Profile.VENDOR})
        category = Category.objects.get(slug="do-cong-nghe")
        shop, _ = Shop.objects.get_or_create(
            name="Logitech Store",
            defaults={
                "owner": owner,
                "description": "Gian hàng demo chuyên chuột Logitech cho học tập, văn phòng và chơi game.",
                "contact": OWNER_EMAIL,
                "shop_type": "DOANH_NGHIEP",
                "status": Shop.ACTIVE,
            },
        )
        if shop.owner_id is None:
            shop.owner = owner
            shop.save(update_fields=["owner"])

        for item in ITEMS:
            folder = ROOT / item["folder"]
            if not folder.is_dir():
                raise FileNotFoundError(f"Thiếu thư mục ảnh: {folder}")
            images = sorted(folder.glob("*"))
            if not images:
                raise FileNotFoundError(f"Thư mục không có ảnh: {folder}")
            product, created_product = Product.objects.get_or_create(
                shop=shop,
                name=item["name"],
                defaults={
                    "category": category,
                    "brand": "Logitech",
                    "tags": "Logitech, chuột, chuột máy tính, chuột gaming, phụ kiện máy tính",
                    "description": item["desc"],
                    "specs": item["specs"],
                    "status": Product.VISIBLE,
                },
            )
            if created_product:
                with images[0].open("rb") as source:
                    product.image.save(images[0].name, process_image(File(source, name=images[0].name)), save=True)
                for position, image_path in enumerate(images[1:], start=1):
                    with image_path.open("rb") as source:
                        image = process_image(File(source, name=image_path.name))
                    ProductImage.objects.create(product=product, image=image, position=position)
                Variant.objects.create(
                    product=product,
                    name="Mặc định",
                    price=item["price"],
                    stock=20,
                    weight=item["dims"][0],
                    length=item["dims"][1],
                    width=item["dims"][2],
                    height=item["dims"][3],
                )
            self.stdout.write(f"{product.pk}: {product.name} — {'imported' if created_product else 'already exists'}")
        self.stdout.write(self.style.SUCCESS(
            f"Shop {shop.name} (ID {shop.pk}); GHN Shop ID chưa gán; sản phẩm: {shop.products.count()}"
        ))
        self.stdout.write(f"Tài khoản demo người bán: {OWNER_EMAIL} / {OWNER_PASSWORD}")
