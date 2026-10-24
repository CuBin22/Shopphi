"""Kiểm tra và chuẩn hóa ảnh sản phẩm do Người bán tải lên.

Không tin phần mở rộng hay Content-Type do trình duyệt gửi: mở file bằng Pillow để xác định định dạng thật
(chỉ JPEG, PNG, WEBP), giới hạn dung lượng và kích thước điểm ảnh (chống ảnh "bom giải nén"), sửa chiều xoay theo EXIF,
nền trong suốt được trải lên nền trắng, thu nhỏ cạnh dài về PRODUCT_IMAGE_MAX_SIDE rồi lưu lại thành JPEG với tên ngẫu nhiên.
Việc ghi lại ảnh gỡ siêu dữ liệu (EXIF/GPS) và mọi nội dung lạ chèn trong file.
"""
import uuid
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000


def process_image(upload) -> ContentFile:
    """Trả về ContentFile JPEG đã chuẩn hóa; ném ValidationError (tiếng Việt, nêu tên file) nếu không hợp lệ."""
    name = getattr(upload, "name", "ảnh")
    if upload.size > settings.PRODUCT_IMAGE_MAX_BYTES:
        raise ValidationError(f"{name}: dung lượng vượt {settings.PRODUCT_IMAGE_MAX_BYTES // (1024 * 1024)} MB.")
    try:
        upload.seek(0)
        probe = Image.open(upload)
        fmt, (w, h) = probe.format, probe.size
        if fmt not in ALLOWED_FORMATS:
            raise ValidationError(f"{name}: chỉ nhận ảnh JPEG, PNG hoặc WEBP.")
        if w * h > MAX_PIXELS:
            raise ValidationError(f"{name}: kích thước điểm ảnh quá lớn.")
        if min(w, h) < settings.PRODUCT_IMAGE_MIN_SIDE:
            raise ValidationError(f"{name}: ảnh quá nhỏ (cạnh ngắn tối thiểu {settings.PRODUCT_IMAGE_MIN_SIDE}px).")
        upload.seek(0)
        img = Image.open(upload)
        img.load()
    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError(f"{name}: không phải file ảnh hợp lệ hoặc file bị hỏng.")
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((settings.PRODUCT_IMAGE_MAX_SIDE, settings.PRODUCT_IMAGE_MAX_SIDE), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, "JPEG", quality=85, optimize=True)
    return ContentFile(buf.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def validate_many(files):
    """Kiểm tra từng file; trả về (danh_sách_ContentFile_đã_chuẩn_hóa, danh_sách_lỗi)."""
    ok, errors = [], []
    for f in files:
        try:
            ok.append(process_image(f))
        except ValidationError as e:
            errors.extend(e.messages)
    return ok, errors


def delete_file_later(storage, name):
    """Xóa file khỏi kho lưu trữ SAU KHI giao dịch cơ sở dữ liệu commit thành công (không xóa nhầm khi rollback)."""
    if name:
        transaction.on_commit(lambda: storage.delete(name))
