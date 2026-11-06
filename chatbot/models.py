from django.conf import settings
from django.db import models
from django.utils import timezone


class ProductEmbedding(models.Model):
    product = models.OneToOneField("catalog.Product", on_delete=models.CASCADE, related_name="chatbot_embedding")
    vector = models.JSONField(default=list)
    content_hash = models.CharField(max_length=64, db_index=True)
    model = models.CharField(max_length=80)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Embedding sản phẩm chatbot"
        verbose_name_plural = "Embedding sản phẩm chatbot"


class ChatLog(models.Model):
    """Nhật ký hội thoại. Chỉ lưu câu hỏi ĐÃ che thông tin cá nhân (QĐ12, NFR05)."""
    OK, REFUSED, ERROR = "OK", "TU_CHOI", "LOI"
    STATUS = [(OK, "Đã trả lời"), (REFUSED, "Từ chối"), (ERROR, "Lỗi LLM")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    question = models.CharField("Câu hỏi (đã che thông tin cá nhân)", max_length=500)
    answer = models.TextField("Câu trả lời", blank=True)
    intent = models.CharField(max_length=20, blank=True)
    product_ids = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=8, choices=STATUS, default=OK)
    provider = models.CharField(max_length=20, blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created", "id"]
        verbose_name = "Hội thoại chatbot"
        verbose_name_plural = "Hội thoại chatbot"
