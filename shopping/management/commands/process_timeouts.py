"""Tác vụ theo hạn: tự chấp nhận yêu cầu hủy quá 24 giờ, tự hoàn thành đơn sau 7 ngày kể từ Đang giao.

    python manage.py process_timeouts            # chạy một lần
    python manage.py process_timeouts --loop 60  # chạy lặp mỗi 60 giây
Chạy lại nhiều lần không gây xử lý trùng.
"""
import time

from django.core.management.base import BaseCommand

from shopping.services import run_timeouts


class Command(BaseCommand):
    help = "Xử lý các đơn và yêu cầu hủy đã quá hạn"

    def add_arguments(self, parser):
        parser.add_argument("--loop", type=int, default=0, help="Chạy lặp, số giây giữa hai lần")

    def handle(self, *args, **opts):
        while True:
            accepted, completed = run_timeouts()
            self.stdout.write(f"Tự chấp nhận hủy: {accepted}; tự hoàn thành: {completed}")
            if not opts["loop"]:
                break
            time.sleep(opts["loop"])
