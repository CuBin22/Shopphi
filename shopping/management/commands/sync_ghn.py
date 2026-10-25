from django.core.management.base import BaseCommand

from shopping.models import Order
from shopping.services import OrderError
from shopping.shipping import sync_order


class Command(BaseCommand):
    help = "Đồng bộ vận đơn GHN chưa kết thúc (dùng khi localhost không nhận webhook)."

    def handle(self, *args, **options):
        orders = Order.objects.filter(carrier="GHN").exclude(tracking_code="").exclude(
            ghn_status__in=["delivered", "cancel", "returned", "damage", "lost"]).exclude(shipping_data={})
        for pk in orders.values_list("pk", flat=True).iterator():
            try:
                order = sync_order(pk)
                self.stdout.write(f"#{pk}: {order.ghn_status}")
            except OrderError as exc:
                self.stderr.write(f"#{pk}: {exc}")
