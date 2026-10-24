from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Product, Shop, Variant


def _lam_moi():
    from .services import refresh_keyword_counts
    transaction.on_commit(refresh_keyword_counts)


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Variant)
@receiver(post_save, sender=Shop)
def cap_nhat_so_san_pham_khop(sender, **kwargs):
    """Số sản phẩm khớp của từ khóa thay đổi khi sản phẩm đổi trạng thái hiển thị (QĐ15)."""
    if kwargs.get("raw"):          # đang nạp dữ liệu (loaddata/import_data): lệnh nạp tự làm mới một lần ở cuối
        return
    _lam_moi()


# ---- dọn file ảnh khi xóa sản phẩm / ảnh phụ (xóa sau khi commit) ----
from django.db.models.signals import post_delete  # noqa: E402

from .images import delete_file_later  # noqa: E402
from .models import ProductImage  # noqa: E402


@receiver(post_delete, sender=Product)
def _xoa_anh_bia(sender, instance, **kwargs):
    if instance.image:
        delete_file_later(instance.image.storage, instance.image.name)


@receiver(post_delete, sender=ProductImage)
def _xoa_anh_phu(sender, instance, **kwargs):
    if instance.image:
        delete_file_later(instance.image.storage, instance.image.name)
