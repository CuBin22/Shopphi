"""Nạp dữ liệu từ file JSON do `export_data` tạo ra vào cơ sở dữ liệu hiện tại (PostgreSQL).

    python manage.py import_data backups/shopphi_20261011_120000.json
    python manage.py import_data file.json --flush --yes     # XÓA sạch dữ liệu hiện có rồi nạp lại

Không dùng --flush: dòng có cùng khóa chính sẽ bị ghi đè, dòng khác giữ nguyên. Toàn bộ việc nạp chạy trong MỘT giao dịch:
lỗi ở bất kỳ dòng nào thì không có gì thay đổi. Sau khi nạp, bộ đếm khóa chính (sequence) của PostgreSQL được đặt lại
và số sản phẩm khớp của từ khóa được làm mới.
"""
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Nạp dữ liệu từ file JSON vào cơ sở dữ liệu"

    def add_arguments(self, parser):
        parser.add_argument("file", help="File JSON tạo bởi export_data")
        parser.add_argument("--flush", action="store_true", help="Xóa toàn bộ dữ liệu hiện có trước khi nạp")
        parser.add_argument("--yes", action="store_true", help="Không hỏi xác nhận khi dùng --flush")

    def handle(self, *args, **opts):
        path = Path(opts["file"])
        if not path.is_file():
            raise CommandError(f"Không thấy file: {path}")
        if path.suffix.lower() != ".json":
            raise CommandError("Chỉ nạp file .json do export_data tạo ra.")
        if opts["flush"] and not opts["yes"]:
            if input("Thao tác này XÓA toàn bộ dữ liệu hiện có. Gõ 'dong y' để tiếp tục: ").strip().lower() != "dong y":
                raise CommandError("Đã hủy.")
        with transaction.atomic():
            if opts["flush"]:
                call_command("flush", interactive=False, verbosity=0)
            call_command("loaddata", str(path.resolve()), verbosity=0)
        from catalog.services import refresh_keyword_counts
        refresh_keyword_counts()
        self.stdout.write(self.style.SUCCESS(f"Đã nạp dữ liệu từ {path}"))
