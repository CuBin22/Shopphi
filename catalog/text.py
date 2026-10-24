"""Chuẩn hóa văn bản tiếng Việt cho tìm kiếm không dấu và từ điển từ khóa."""
import re
import unicodedata

# Từ khóa hợp lệ: chữ, số, khoảng trắng, dấu gạch nối (không ký tự đặc biệt).
KEYWORD_RE = re.compile(r"^[\w\s-]+$", re.UNICODE)


def bo_dau(s: str) -> str:
    s = (s or "").replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def chuan_hoa(s: str) -> str:
    """Gộp khoảng trắng, bỏ khoảng đầu/cuối, chữ thường."""
    return re.sub(r"\s+", " ", s or "").strip().lower()


def khong_dau(s: str) -> str:
    return bo_dau(chuan_hoa(s))


def tu_khoa_hop_le(q: str) -> bool:
    return 2 <= len(q) <= 100 and bool(KEYWORD_RE.match(q))
