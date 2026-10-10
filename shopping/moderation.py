"""Quản trị sàn (UC16, UC17, UC18): duyệt / từ chối / khóa / mở khóa gian hàng, gỡ / khôi phục sản phẩm.
Mọi thao tác chỉ dành cho Quản trị viên, bắt buộc lý do khi từ chối, khóa, gỡ, khôi phục; có nhật ký (AdminLog) và thông báo cho Người bán."""
from django.db import transaction

from accounts.models import Profile
from accounts.utils import get_role
from catalog.models import AdminLog, Product, Shop

from .services import OrderError, notify


def _check_admin(user):
    if user is None or not user.is_authenticated or get_role(user) != Profile.ADMIN:
        raise OrderError("Chỉ Quản trị viên được thực hiện thao tác này.")


def write_log(actor, target_type, target_id, label, action, reason=""):
    AdminLog.objects.create(actor=actor, target_type=target_type, target_id=target_id,
                            target_label=(label or "")[:200], action=action, reason=(reason or "")[:255])


# chuyển trạng thái gian hàng hợp lệ (khớp ràng buộc ở SQL v3)
SHOP_FLOW = {
    Shop.PENDING: {Shop.ACTIVE, Shop.REJECTED},
    Shop.REJECTED: {Shop.PENDING},
    Shop.ACTIVE: {Shop.LOCKED},
    Shop.LOCKED: {Shop.ACTIVE},
}
SHOP_ACTION = {Shop.ACTIVE: "DUYET_MO_KHOA", Shop.REJECTED: "TU_CHOI_XET_DUYET", Shop.LOCKED: "KHOA_GIAN_HANG", Shop.PENDING: "GUI_LAI_XET_DUYET"}


def set_shop_status(admin, shop_id, new_status, reason=""):
    _check_admin(admin)
    reason = (reason or "").strip()
    with transaction.atomic():
        shop = Shop.objects.select_for_update(of=("self",)).select_related("owner").filter(pk=shop_id).first()
        if shop is None:
            raise OrderError("Không tìm thấy gian hàng.")
        if new_status not in SHOP_FLOW.get(shop.status, set()):
            raise OrderError(f"Không được chuyển gian hàng từ \"{shop.get_status_display()}\" sang trạng thái này.")
        if new_status in (Shop.REJECTED, Shop.LOCKED) and not reason:
            raise OrderError("Bắt buộc ghi lý do khi từ chối hoặc khóa gian hàng.")
        old = shop.status
        shop.status = new_status
        shop.status_reason = reason[:255] if new_status in (Shop.REJECTED, Shop.LOCKED) else ""
        shop.save(update_fields=["status", "status_reason"])
        write_log(admin, AdminLog.SHOP, shop.pk, shop.name, f"{SHOP_ACTION[new_status]} ({old}->{new_status})", reason)
        text = {Shop.ACTIVE: "đã được duyệt / mở khóa, bạn có thể đăng bán.",
                Shop.REJECTED: f"bị từ chối xét duyệt. Lý do: {reason}",
                Shop.LOCKED: f"bị khóa, toàn bộ sản phẩm ngừng hiển thị. Lý do: {reason}",
                Shop.PENDING: "chuyển sang chờ duyệt."}[new_status]
        notify(shop.owner, f'Gian hàng "{shop.name}" {text}', "/quan-ly/")
    return shop


def remove_product(admin, product_id, reason):
    """Gỡ sản phẩm vi phạm: không còn trong tìm kiếm, gợi ý từ khóa, gợi ý sản phẩm, chatbot."""
    _check_admin(admin)
    reason = (reason or "").strip()
    if not reason:
        raise OrderError("Bắt buộc ghi lý do gỡ sản phẩm.")
    with transaction.atomic():
        p = Product.objects.select_for_update(of=("self",)).select_related("shop__owner").filter(pk=product_id).first()
        if p is None:
            raise OrderError("Không tìm thấy sản phẩm.")
        if p.status == Product.REMOVED:
            raise OrderError("Sản phẩm đã bị gỡ trước đó.")
        p.status, p.removal_reason = Product.REMOVED, reason[:255]
        p.save()
        write_log(admin, AdminLog.PRODUCT, p.pk, p.name, "GO_SAN_PHAM", reason)
        notify(p.shop.owner, f'Sản phẩm "{p.name}" bị gỡ. Lý do: {reason}', "/quan-ly/san-pham/")
    return p


def restore_product(admin, product_id, reason):
    """Khôi phục sản phẩm đã gỡ: đưa về trạng thái ẨN, Người bán tự chọn Hiển thị lại (khớp SQL v3)."""
    _check_admin(admin)
    reason = (reason or "").strip()
    if not reason:
        raise OrderError("Bắt buộc ghi lý do khôi phục sản phẩm.")
    with transaction.atomic():
        p = Product.objects.select_for_update(of=("self",)).select_related("shop__owner").filter(pk=product_id).first()
        if p is None:
            raise OrderError("Không tìm thấy sản phẩm.")
        if p.status != Product.REMOVED:
            raise OrderError("Sản phẩm không ở trạng thái Bị gỡ.")
        p.status, p.removal_reason = Product.HIDDEN, ""
        p.save()
        write_log(admin, AdminLog.PRODUCT, p.pk, p.name, "KHOI_PHUC_SAN_PHAM", reason)
        notify(p.shop.owner, f'Sản phẩm "{p.name}" đã được khôi phục (đang Ẩn), bạn có thể chọn Hiển thị lại.', "/quan-ly/san-pham/")
    return p


def set_keyword_visibility(admin, keyword_id, visible, reason=""):
    """UC18: ẩn / hiện từ khóa gợi ý, ghi nhật ký."""
    from catalog.models import Keyword
    _check_admin(admin)
    reason = (reason or "").strip()
    with transaction.atomic():
        k = Keyword.objects.select_for_update().filter(pk=keyword_id).first()
        if k is None:
            raise OrderError("Không tìm thấy từ khóa.")
        if not visible and not reason:
            raise OrderError("Cần nhập lý do khi ẩn từ khóa.")
        k.visible = visible
        k.hidden_reason = "" if visible else reason[:255]
        k.hidden_by = None if visible else admin
        k.save()
        write_log(admin, AdminLog.KEYWORD, k.pk, k.phrase, "HIEN_TU_KHOA" if visible else "AN_TU_KHOA", reason)
    return k
