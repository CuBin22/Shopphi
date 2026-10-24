"""Kiểm tra kết nối cơ sở dữ liệu và số dòng của từng bảng chính.

    python manage.py check_db
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Kiểm tra kết nối PostgreSQL và thống kê số dòng dữ liệu"

    def handle(self, *args, **opts):
        db = connection.settings_dict
        try:
            with connection.cursor() as cur:
                cur.execute("select version()" if connection.vendor == "postgresql" else "select sqlite_version()")
                version = cur.fetchone()[0]
        except Exception as e:  # noqa: BLE001
            raise CommandError(
                f"Không kết nối được cơ sở dữ liệu ({connection.vendor}, {db.get('HOST')}:{db.get('PORT')}/{db.get('NAME')}): {e}\n"
                "Kiểm tra PostgreSQL đã chạy, đã tạo database (CREATE DATABASE \"Shopphi\" ENCODING 'UTF8';) "
                "và biến môi trường DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.")
        self.stdout.write(self.style.SUCCESS(f"Kết nối OK: {connection.vendor} - {version}"))
        self.stdout.write(f"Database: {db.get('NAME')} @ {db.get('HOST')}:{db.get('PORT')} (user {db.get('USER')})")
        from django.db.migrations.executor import MigrationExecutor
        pending = MigrationExecutor(connection).migration_plan(
            MigrationExecutor(connection).loader.graph.leaf_nodes())
        if pending:
            self.stdout.write(self.style.WARNING(f"Còn {len(pending)} migration chưa chạy: hãy chạy `python manage.py migrate`."))
            return
        for label in ("auth.User", "accounts.Profile", "catalog.Shop", "catalog.Category", "catalog.Product", "catalog.Variant",
                      "shopping.Order", "shopping.OrderGroup", "shopping.PaymentTransaction", "shopping.Coupon",
                      "shopping.Review", "catalog.BehaviorLog", "chatbot.ChatLog"):
            try:
                self.stdout.write(f"  {label:<32}{apps.get_model(label).objects.count():>8}")
            except LookupError:
                pass
