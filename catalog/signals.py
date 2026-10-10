from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Product, Shop, Variant


ENABLED = True  # lệnh seed_demo tạm tắt để không làm mới từ khóa sau mỗi lần lưu


def _lam_moi():
    if not ENABLED:
        return
    from .services import refresh_keyword_counts
    transaction.on_commit(refresh_keyword_counts)


@receiver([post_save, post_delete], sender=Product)
@receiver([post_save, post_delete], sender=Variant)
@receiver(post_save, sender=Shop)
def cap_nhat_so_san_pham_khop(sender, **kwargs):
    """Số sản phẩm khớp của từ khóa thay đổi khi sản phẩm đổi trạng thái hiển thị (QĐ15)."""
    _lam_moi()
