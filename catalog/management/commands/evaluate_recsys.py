"""Đánh giá mô hình gợi ý trên Retail Rocket (Precision@K, Recall@K, NDCG@K, HitRate@K), so sánh với phương án dự phòng.

    python manage.py evaluate_recsys --events D:/data/retailrocket/events.csv --k 10
    python manage.py evaluate_recsys --demo                 # chạy thử bằng dữ liệu giả lập, chưa cần tải dữ liệu
Tải bộ dữ liệu: https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset (tệp events.csv).
"""
import json

from django.core.management.base import BaseCommand, CommandError

from catalog import recsys_eval as ev


class Command(BaseCommand):
    help = "Đánh giá mô hình gợi ý sản phẩm bằng các chỉ số xếp hạng"

    def add_arguments(self, parser):
        parser.add_argument("--events", help="Đường dẫn events.csv của Retail Rocket")
        parser.add_argument("--demo", action="store_true", help="Dùng dữ liệu giả lập")
        parser.add_argument("--k", type=int, default=10)
        parser.add_argument("--ratio", type=float, default=0.8, help="Tỷ lệ thời gian dùng để huấn luyện")
        parser.add_argument("--min-history", type=int, default=3, help="Số sản phẩm tối thiểu đã tương tác để đánh giá một người dùng")
        parser.add_argument("--max-rows", type=int, default=0, help="Chỉ đọc N dòng đầu (0 = đọc hết)")
        parser.add_argument("--max-users", type=int, default=2000, help="Số người dùng tối đa dùng để đánh giá")
        parser.add_argument("--json", help="Ghi kết quả ra tệp JSON")

    def handle(self, *args, **o):
        if o["demo"]:
            events = ev.synthetic_events()
        elif o["events"]:
            events = ev.load_events(o["events"], o["max_rows"] or None)
        else:
            raise CommandError("Cần --events <events.csv> hoặc --demo")
        if len(events) < 100:
            raise CommandError("Dữ liệu quá ít để đánh giá")
        res = ev.evaluate(events, o["k"], o["ratio"], o["min_history"], o["max_users"])
        self.stdout.write(ev.format_report(res))
        if o["json"]:
            with open(o["json"], "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            self.stdout.write(f"Đã ghi {o['json']}")
