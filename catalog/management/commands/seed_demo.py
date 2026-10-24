"""Nạp dữ liệu mẫu: gian hàng, sản phẩm, từ điển từ khóa và log hành vi giả lập.

    python manage.py seed_demo --reset
"""
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog import signals
from catalog.models import BehaviorLog, Category, Keyword, Product, Shop, Variant
from catalog.services import refresh_keyword_counts

DEMO_PASSWORD = "demo12345"
VENDOR_USERS = [f"ban{i}@shopphi.vn" for i in range(1, 6)]       # chủ 5 gian hàng theo thứ tự SHOPS
CUSTOMER_USERS = [("khach1@shopphi.vn", "Nguyễn Minh Anh"), ("khach2@shopphi.vn", "Trần Quốc Bảo"),
                  ("khach3@shopphi.vn", "Lê Thu Hà")]

SHOPS = ["Sóng Audio", "Cổng Sạc", "Gia Dụng Mộc An", "Bếp Nhà Xanh", "Hộp Đồ Chơi Mây"]

CATEGORIES = [("do-cong-nghe", "Đồ công nghệ"), ("do-gia-dung", "Đồ gia dụng"), ("do-choi", "Đồ chơi")]

# (gian hàng, danh mục, tên, thương hiệu, thẻ, mô tả, thông số, [(biến thể, giá, tồn)])
PRODUCTS = [
    (0, "do-cong-nghe", "Tai nghe Bluetooth Sóng A1", "Sóng", "tai nghe, bluetooth, không dây",
     "Tai nghe không dây nhỏ gọn, âm bass dày, dùng thoải mái cả ngày.",
     "Kết nối: Bluetooth 5.3\nPin: 30 giờ (kèm hộp sạc)\nChống nước: IPX4",
     [("Đen", 590000, 40), ("Trắng", 590000, 25)]),
    (0, "do-cong-nghe", "Tai nghe gaming Sóng G7", "Sóng", "tai nghe, gaming, có mic",
     "Tai nghe chụp tai có micro khử ồn, đệm tai êm cho các buổi chơi dài.",
     "Kết nối: USB và jack 3.5 mm\nDriver: 50 mm\nĐèn: RGB",
     [("Đen", 890000, 18)]),
    (0, "do-cong-nghe", "Tai nghe có dây Sóng E3", "Sóng", "tai nghe, có dây, jack 3.5",
     "Tai nghe nhét tai có dây, bền và rẻ, hợp để học và làm việc.",
     "Kết nối: Jack 3.5 mm\nDây dài: 1.2 m",
     [("Đen", 190000, 60)]),
    (0, "do-cong-nghe", "Loa Bluetooth mini Sóng Pop", "Sóng", "loa, bluetooth, mini",
     "Loa nhỏ bằng lòng bàn tay, âm to rõ, mang theo đi dã ngoại.",
     "Công suất: 10 W\nPin: 12 giờ\nChống nước: IPX5",
     [("Xanh", 450000, 30), ("Hồng", 450000, 12)]),
    (1, "do-cong-nghe", "Sạc dự phòng Cổng 10000mAh", "Cổng", "sạc dự phòng, pin dự phòng",
     "Pin dự phòng mỏng nhẹ, sạc nhanh hai chiều, có đèn báo dung lượng.",
     "Dung lượng: 10000 mAh\nCổng ra: USB-A, USB-C\nSạc nhanh: 22.5 W",
     [("Trắng", 350000, 50), ("Đen", 350000, 35)]),
    (1, "do-cong-nghe", "Củ sạc nhanh 33W Cổng", "Cổng", "củ sạc, sạc nhanh",
     "Củ sạc nhanh GaN nhỏ gọn, sạc đủ cho điện thoại và máy tính bảng.",
     "Công suất: 33 W\nCổng: USB-C\nChuẩn: PD 3.0",
     [("Trắng", 220000, 70)]),
    (1, "do-cong-nghe", "Cáp sạc USB-C bện dù", "Cổng", "cáp sạc, usb-c",
     "Cáp bện dù chống đứt gãy, truyền dữ liệu và sạc nhanh.",
     "Chuẩn: USB-C to USB-C\nCông suất tối đa: 60 W",
     [("1 m", 90000, 120), ("2 m", 130000, 80)]),
    (1, "do-cong-nghe", "Ốp lưng điện thoại trong suốt", "Cổng", "ốp lưng, điện thoại",
     "Ốp dẻo trong suốt, chống ố vàng, viền cao bảo vệ camera.",
     "Chất liệu: TPU\nTương thích: nhiều dòng điện thoại phổ biến",
     [("Trong suốt", 80000, 100)]),
    (1, "do-cong-nghe", "Chuột không dây Cổng M2", "Cổng", "chuột, không dây, văn phòng",
     "Chuột không dây yên tĩnh, bấm êm, phù hợp văn phòng.",
     "Kết nối: 2.4 GHz\nPin: 1 viên AA\nDPI: 1600",
     [("Xám", 260000, 45)]),
    (0, "do-cong-nghe", "Bàn phím cơ Sóng K87", "Sóng", "bàn phím, bàn phím cơ",
     "Bàn phím cơ 87 phím, switch đỏ êm, đèn nền trắng.",
     "Layout: TKL 87 phím\nSwitch: Red\nKết nối: USB-C",
     [("Đen", 1250000, 15)]),
    (2, "do-gia-dung", "Nồi chiên không dầu 5L", "Mộc An", "nồi chiên, nồi chiên không dầu",
     "Nồi chiên không dầu dung tích 5 lít, chiên giòn ít dầu, dễ vệ sinh.",
     "Dung tích: 5 lít\nCông suất: 1500 W\nNhiệt độ: 80-200 độ C",
     [("Đen", 1790000, 22)]),
    (2, "do-gia-dung", "Ấm đun siêu tốc 1.8L", "Mộc An", "ấm đun, ấm siêu tốc",
     "Ấm inox 304, tự ngắt khi sôi, đun 1.8 lít chỉ vài phút.",
     "Dung tích: 1.8 lít\nCông suất: 1800 W\nChất liệu: Inox 304",
     [("Bạc", 320000, 40)]),
    (3, "do-gia-dung", "Máy xay sinh tố mini", "Bếp Nhà Xanh", "máy xay, sinh tố",
     "Máy xay cốc rời 400 ml, xay trái cây và đá viên, mang đi được.",
     "Dung tích: 400 ml\nCông suất: 300 W",
     [("Xanh lá", 490000, 28)]),
    (3, "do-gia-dung", "Bình giữ nhiệt 750ml", "Bếp Nhà Xanh", "bình giữ nhiệt",
     "Bình inox hai lớp giữ nóng 12 giờ, giữ lạnh 24 giờ.",
     "Dung tích: 750 ml\nChất liệu: Inox 304",
     [("Xanh", 210000, 55), ("Be", 210000, 40)]),
    (2, "do-gia-dung", "Nồi cơm điện 1.2L", "Mộc An", "nồi cơm, nồi cơm điện",
     "Nồi cơm điện nắp gài, lòng nồi chống dính, nấu 3-4 người ăn.",
     "Dung tích: 1.2 lít\nCông suất: 500 W",
     [("Trắng", 890000, 20)]),
    (3, "do-gia-dung", "Máy hút bụi cầm tay", "Bếp Nhà Xanh", "máy hút bụi, hút bụi",
     "Máy hút bụi không dây nhẹ, hút sofa, nệm và xe hơi.",
     "Lực hút: 12 kPa\nPin: 35 phút",
     [("Xám", 1490000, 14)]),
    (2, "do-gia-dung", "Đèn bàn LED chống cận", "Mộc An", "đèn bàn, đèn led",
     "Đèn bàn LED ba mức sáng, ánh sáng dịu, chống mỏi mắt.",
     "Công suất: 9 W\nNhiệt độ màu: 3000-6000 K",
     [("Trắng", 280000, 36)]),
    (3, "do-gia-dung", "Bộ dao nhà bếp 5 món", "Bếp Nhà Xanh", "dao, bộ dao, nhà bếp",
     "Bộ dao inox sắc bén gồm 5 món, kèm đế cắm dao gỗ.",
     "Số món: 5\nChất liệu: Inox",
     [("Bộ 5 món", 340000, 25)]),
    (4, "do-choi", "Bộ xếp hình 500 mảnh", "Mây", "xếp hình, lắp ráp",
     "Bộ xếp hình sáng tạo 500 mảnh, hợp bé từ 6 tuổi.",
     "Số mảnh: 500\nĐộ tuổi: 6+",
     [("Mặc định", 320000, 0)]),
    (4, "do-choi", "Xe điều khiển từ xa", "Mây", "xe điều khiển, xe đồ chơi",
     "Xe địa hình điều khiển từ xa, pin sạc, chạy mọi địa hình.",
     "Tầm điều khiển: 30 m\nPin: sạc USB",
     [("Đỏ", 420000, 30), ("Xanh", 420000, 18)]),
    (4, "do-choi", "Robot biến hình", "Mây", "robot, biến hình",
     "Robot biến hình thành xe chỉ trong vài bước, khớp chắc chắn.",
     "Chất liệu: Nhựa ABS\nĐộ tuổi: 5+",
     [("Mặc định", 380000, 24)]),
    (4, "do-choi", "Bộ ghép hình 1000 mảnh", "Mây", "ghép hình, puzzle",
     "Tranh ghép 1000 mảnh in sắc nét, thư giãn cuối tuần.",
     "Số mảnh: 1000\nKích thước: 50 x 70 cm",
     [("Mặc định", 180000, 50)]),
    (4, "do-choi", "Búp bê vải", "Mây", "búp bê, gấu bông",
     "Búp bê vải mềm, an toàn cho bé, giặt được.",
     "Chiều cao: 35 cm\nChất liệu: Vải cotton",
     [("Mặc định", 150000, 60)]),
    (4, "do-choi", "Bộ đồ chơi nhà bếp mini", "Mây", "đồ chơi nhà bếp, nấu ăn",
     "Bộ nồi chảo thu nhỏ để bé tập nấu ăn, nhựa an toàn.",
     "Số món: 18\nĐộ tuổi: 3+",
     [("Mặc định", 260000, 33)]),
    (4, "do-choi", "Bộ xếp hình robot 300 mảnh", "Mây", "xếp hình, robot, lắp ráp",
     "Lắp ráp robot 300 mảnh, có hướng dẫn từng bước.",
     "Số mảnh: 300\nĐộ tuổi: 7+",
     [("Mặc định", 280000, 40)]),
]

# Nhóm sản phẩm được xem cùng nhau (chỉ số theo thứ tự trong PRODUCTS) để tạo log hành vi giả lập
CLUSTERS = [
    [0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 16], [10, 11, 12, 13, 14, 17],
    [18, 19, 20, 21, 22, 23, 24], [0, 4, 3, 5], [10, 14, 15, 16],
]

# (cụm từ khóa, tần suất)
KEYWORDS = [
    ("tai nghe", 120), ("tai nghe bluetooth", 42), ("tai nghe gaming", 27), ("tai nghe có dây", 15),
    ("sạc dự phòng", 31), ("củ sạc nhanh", 12), ("cáp sạc usb-c", 9), ("loa bluetooth", 18),
    ("chuột không dây", 14), ("bàn phím cơ", 16), ("ốp lưng điện thoại", 19),
    ("nồi chiên không dầu", 38), ("nồi cơm điện", 17), ("ấm siêu tốc", 11), ("máy xay sinh tố", 13),
    ("bình giữ nhiệt", 10), ("máy hút bụi", 8), ("đèn bàn led", 9),
    ("bộ xếp hình", 24), ("xếp hình robot", 7), ("xe điều khiển", 12), ("robot biến hình", 7),
    ("ghép hình", 6), ("búp bê", 5),
    ("iphone 15", 4),            # chưa có sản phẩm khớp: không được gợi ý
    ("tai nghe nhái", 5),        # chỉ khớp sản phẩm của gian hàng bị khóa: không được gợi ý
]


class Command(BaseCommand):
    help = "Nạp dữ liệu mẫu cho Shopphi"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Xóa dữ liệu mẫu cũ trước khi nạp")

    def handle(self, *args, **opts):
        signals.ENABLED = False
        try:
            with transaction.atomic():
                self._nap(opts)
        finally:
            signals.ENABLED = True

    def _nap(self, opts):
        if opts["reset"]:
            from chatbot.models import ChatLog
            from shopping import models as sm
            for m in (sm.Review, sm.CouponUse, sm.CancelRequest, sm.OrderStatusLog, sm.OrderItem, sm.Order, sm.PaymentTransaction, sm.OrderGroup,
                      sm.CartItem, sm.Notification, sm.Coupon, ChatLog):
                m.objects.all().delete()
            get_user_model().objects.filter(username__in=VENDOR_USERS + [u for u, _ in CUSTOMER_USERS]).delete()
            from catalog.models import AdminLog
            AdminLog.objects.all().delete()
            BehaviorLog.objects.all().delete()
            Keyword.objects.all().delete()
            Product.objects.all().delete()
            Shop.objects.all().delete()
            Category.objects.all().delete()
        elif Product.objects.exists():
            self.stdout.write(self.style.WARNING("Đã có dữ liệu. Dùng --reset để nạp lại."))
            return

        cats = {slug: Category.objects.create(slug=slug, name=name, order=i)
                for i, (slug, name) in enumerate(CATEGORIES)}
        from accounts.models import Profile
        User = get_user_model()
        shops = []
        for n, uname in zip(SHOPS, VENDOR_USERS):
            u = User.objects.create_user(uname, uname, DEMO_PASSWORD, first_name=f"Chủ {n}")
            Profile.objects.create(user=u, role=Profile.VENDOR)
            shops.append(Shop.objects.create(name=n, status=Shop.ACTIVE, owner=u, pickup_address="Quận 1, TP.HCM",
                                             contact=uname, shop_type="DOANH_NGHIEP"))
        customers = []
        for uname, full in CUSTOMER_USERS:
            u = User.objects.create_user(uname, uname, DEMO_PASSWORD, first_name=full)
            Profile.objects.create(user=u, role=Profile.CUSTOMER, default_address="12 Nguyễn Huệ, Quận 1, TP.HCM")
            customers.append(u)

        products = []
        for sh, cat, name, brand, tags, desc, specs, variants in PRODUCTS:
            p = Product.objects.create(shop=shops[sh], category=cats[cat], name=name, brand=brand,
                                       tags=tags, description=desc, specs=specs)
            for vn, price, stock in variants:
                Variant.objects.create(product=p, name=vn, price=price, stock=stock)
            products.append(p)

        # Gian hàng bị khóa: sản phẩm không được hiện ở tìm kiếm, gợi ý, từ khóa
        locked = Shop.objects.create(name="Kho Hàng Cũ", status=Shop.LOCKED)
        bad = Product.objects.create(shop=locked, category=cats["do-cong-nghe"], name="Tai nghe nhái",
                                     brand="N/A", tags="tai nghe, nhái", description="Sản phẩm vi phạm.")
        Variant.objects.create(product=bad, name="Mặc định", price=99000, stock=10)

        for phrase, freq in KEYWORDS:
            Keyword.objects.create(phrase=phrase, frequency=freq)
        Keyword.objects.create(phrase="loa", frequency=20, visible=False, hidden_reason="Từ khóa quá chung")

        # Log hành vi giả lập: mỗi phiên thường quan tâm 1-2 nhóm sản phẩm
        rnd = random.Random(7)
        logs = []
        for i in range(90):
            sk = f"seed-{i:04d}"
            for cluster in rnd.sample(CLUSTERS, rnd.choice([1, 1, 2])):
                for idx in rnd.sample(cluster, rnd.randint(2, min(5, len(cluster)))):
                    p = products[idx]
                    logs.append(BehaviorLog(session_key=sk, product=p, type=BehaviorLog.VIEW))
                    if rnd.random() < 0.55:
                        logs.append(BehaviorLog(session_key=sk, product=p, type=BehaviorLog.CLICK, source="seed"))
                    if rnd.random() < 0.30:
                        logs.append(BehaviorLog(session_key=sk, product=p, type=BehaviorLog.ADD))
                    if rnd.random() < 0.12:
                        logs.append(BehaviorLog(session_key=sk, product=p, type=BehaviorLog.PURCHASE, source="DON_HANG"))
        BehaviorLog.objects.bulk_create(logs)

        refresh_keyword_counts()

        admin_user = User.objects.filter(username="admin").first()
        if not admin_user:
            admin_user = User.objects.create_superuser("admin", "admin@example.com", "admin12345")
            self.stdout.write("Đã tạo tài khoản quản trị: admin / admin12345")
        Profile.objects.get_or_create(user=admin_user, defaults={"role": Profile.ADMIN})

        self._coupons_and_orders(shops, products, customers, rnd)

        self.stdout.write(self.style.SUCCESS(
            f"Xong: {len(products)} sản phẩm, {Keyword.objects.count()} từ khóa, {len(logs)} dòng log hành vi. "
            f"Tài khoản mẫu (mật khẩu {DEMO_PASSWORD}): {CUSTOMER_USERS[0][0]} (khách), {VENDOR_USERS[0]} (người bán), admin / admin12345."))

    def _coupons_and_orders(self, shops, products, customers, rnd):
        """Mã giảm giá mẫu và vài đơn đã hoàn thành/đã hủy rải trong 14 ngày để trang thống kê có số liệu."""
        from shopping import models as sm
        from shopping.services import SHIPPING_FEE
        now = timezone.now()
        sm.Coupon.objects.create(code="CHAOSHOPPHI", scope="TOAN_SAN", kind="PHAN_TRAM", value=10, max_discount=50000,
                                 min_order=200000, starts=now - timedelta(days=1), expires=now + timedelta(days=90), max_uses=100)
        sm.Coupon.objects.create(code="GIAM30K", scope="TOAN_SAN", kind="SO_TIEN", value=30000, min_order=100000,
                                 starts=now - timedelta(days=1), expires=now + timedelta(days=90), max_uses=3)
        sm.Coupon.objects.create(code="SONG50K", scope="GIAN_HANG", shop=shops[0], kind="SO_TIEN", value=50000,
                                 min_order=500000, starts=now - timedelta(days=1), expires=now + timedelta(days=60), max_uses=50)
        for n in range(14):
            cust = customers[n % len(customers)]
            idxs = rnd.sample(range(len(PRODUCTS)), 2)
            when = now - timedelta(days=13 - n, hours=rnd.randint(0, 5))
            by_shop = {}
            for i in idxs:
                if PRODUCTS[i][7][0][2] > 0:
                    by_shop.setdefault(PRODUCTS[i][0], []).append(products[i])
            if not by_shop:
                continue
            group = sm.OrderGroup.objects.create(user=cust, recipient_name=cust.first_name, recipient_phone="0900000000",
                                                 address="12 Nguyễn Huệ, Quận 1, TP.HCM", created=when)
            g_sub = 0
            for sh, plist in by_shop.items():
                order = sm.Order.objects.create(group=group, shop=shops[sh], subtotal=0, shipping_fee=SHIPPING_FEE, total=0, created=when)
                sub = 0
                for p in plist:
                    v = p.variants.first()
                    sm.OrderItem.objects.create(order=order, variant=v, product_name=p.name, variant_name=v.name, unit_price=v.price, qty=1)
                    sub += int(v.price)
                canceled = n % 5 == 4
                order.subtotal, order.total = sub, sub + SHIPPING_FEE
                order.status = "DA_HUY" if canceled else "HOAN_THANH"
                order.payment_status = "CHUA_THANH_TOAN" if canceled else "DA_THANH_TOAN"
                order.cancel_reason = "Khách đổi ý" if canceled else ""
                order.save()
                sm.OrderStatusLog.objects.create(order=order, at=when, old_status="", new_status="CHO_XAC_NHAN", actor=cust)
                if canceled:
                    sm.OrderStatusLog.objects.create(order=order, at=when + timedelta(hours=1), old_status="CHO_XAC_NHAN",
                                                     new_status="DA_HUY", actor=cust if n % 2 else None, note="Khách đổi ý")
                else:
                    sm.OrderStatusLog.objects.create(order=order, at=when + timedelta(hours=2), old_status="CHO_XAC_NHAN",
                                                     new_status="DA_XAC_NHAN", actor=shops[sh].owner)
                    sm.OrderStatusLog.objects.create(order=order, at=when + timedelta(days=1), old_status="DA_XAC_NHAN",
                                                     new_status="DANG_GIAO", actor=shops[sh].owner)
                    sm.OrderStatusLog.objects.create(order=order, at=when + timedelta(days=2), old_status="DANG_GIAO",
                                                     new_status="HOAN_THANH", actor=cust)
                    for p in plist:
                        if rnd.random() < 0.6 and not sm.Review.objects.filter(user=cust, product=p).exists():
                            sm.Review.objects.create(user=cust, product=p, order=order, rating=rnd.choice([4, 5, 5, 3]),
                                                     comment=rnd.choice(["Dùng tốt, giao nhanh.", "Đúng mô tả.", "Hài lòng với giá này.", ""]),
                                                     created=when + timedelta(days=3))
                g_sub += order.total
            group.subtotal = g_sub - SHIPPING_FEE * len(by_shop)
            group.shipping_fee = SHIPPING_FEE * len(by_shop)
            group.total = g_sub
            group.save()
