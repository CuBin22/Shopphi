"""Sao lưu dữ liệu ứng dụng ra một file JSON (UTF-8) để nạp lại bằng `import_data`.

    python manage.py export_data                         # ghi vào backups/shopphi_<ngày giờ>.json
    python manage.py export_data --out D:/sao_luu.json
    python manage.py export_data --no-logs               # bỏ log hành vi và hội thoại chatbot (file nhỏ hơn)

Chỉ sao lưu DỮ LIỆU (bảng do Django quản lý); ảnh sản phẩm nằm ở thư mục media/ cần sao chép riêng.
Muốn sao lưu cả cấu trúc bảng ở mức PostgreSQL thì dùng thêm: pg_dump -U postgres -d Shopphi -F c -f shopphi.dump
"""
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

EXCLUDE = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]
LOG_MODELS = ["catalog.behaviorlog", "chatbot.chatlog"]


class Command(BaseCommand):
    help = "Xuất toàn bộ dữ liệu ứng dụng ra file JSON"

    def add_arguments(self, parser):
        parser.add_argument("--out", help="Đường dẫn file JSON (mặc định backups/shopphi_<thời gian>.json)")
        parser.add_argument("--no-logs", action="store_true", help="Không xuất log hành vi và hội thoại chatbot")

    def handle(self, *args, **opts):
        out = Path(opts["out"]) if opts["out"] else Path(settings.BASE_DIR) / "backups" / f"shopphi_{datetime.now():%Y%m%d_%H%M%S}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        exclude = EXCLUDE + (LOG_MODELS if opts["no_logs"] else [])
        with open(out, "w", encoding="utf-8") as f:
            call_command("dumpdata", indent=2, exclude=exclude, use_natural_foreign_keys=True, stdout=f)
        self.stdout.write(self.style.SUCCESS(f"Đã xuất dữ liệu: {out} ({out.stat().st_size:,} byte)"))
