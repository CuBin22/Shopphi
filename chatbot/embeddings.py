"""Gemini embedding helpers and the small-catalog vector cache."""
import hashlib
import json
import logging
import math
import os
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from .models import ProductEmbedding

logger = logging.getLogger(__name__)
EMBEDDING_DIMENSIONS = 768
EMBEDDING_TIMEOUT = 20


def product_embedding_text(product) -> str:
    """Public, relatively stable product text; live price and stock are intentionally excluded."""
    variants = " ".join(variant.name for variant in product.variants.all())
    text = (
        f"Sản phẩm: {product.name}. Danh mục: {product.category.name}. "
        f"Thương hiệu: {product.brand}. Thẻ: {product.tags}. "
        f"Gian hàng: {product.shop.name}. Biến thể: {variants}. "
        f"Mô tả: {product.description}. Thông số: {product.specs}"
    )
    return text[:7000]


def _embedding_model() -> str:
    return getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")


def _post_embedding(endpoint: str, body: dict) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("Chưa cấu hình GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(_embedding_model(), safe='')}:" + endpoint
    request = urllib.request.Request(
        url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"content-type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=EMBEDDING_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"Gemini embedding HTTP {exc.code}: {detail}") from exc


def _embedding_config(task_type: str) -> dict:
    return {"taskType": task_type, "autoTruncate": True}


def _embedding_request(text: str, task_type: str) -> dict:
    return {
        "model": f"models/{_embedding_model()}",
        "content": {"parts": [{"text": text}]},
        "embedContentConfig": _embedding_config(task_type),
        # Gemini's REST endpoint currently honors this legacy field for dimension reduction.
        "outputDimensionality": EMBEDDING_DIMENSIONS,
    }


def embed_text(text: str, task_type: str) -> list[float]:
    data = _post_embedding("embedContent", _embedding_request(text, task_type))
    vector = data.get("embedding", {}).get("values", [])
    if not vector or not all(math.isfinite(float(value)) for value in vector):
        raise RuntimeError("Gemini trả về embedding không hợp lệ")
    return [float(value) for value in vector]


def embed_texts(texts: list[str], task_type: str) -> list[list[float]]:
    if not texts:
        return []
    data = _post_embedding("batchEmbedContents", {
        "requests": [_embedding_request(text, task_type) for text in texts]
    })
    vectors = [item.get("values", []) for item in data.get("embeddings", [])]
    if len(vectors) != len(texts) or any(
        not vector or not all(math.isfinite(float(value)) for value in vector) for vector in vectors
    ):
        raise RuntimeError("Gemini trả về danh sách embedding không hợp lệ")
    return [[float(value) for value in vector] for vector in vectors]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def refresh_product_embeddings(products) -> dict[int, list[float]]:
    """Batch-create absent/stale vectors, then return cached vectors indexed by product ID."""
    products = list(products)
    if not products or not os.environ.get("GEMINI_API_KEY"):
        return {}

    # Include the vector size in the cache version so changing dimensions cannot
    # leave old vectors silently incompatible with new query vectors.
    model = f"{_embedding_model()}:{EMBEDDING_DIMENSIONS}"
    rows = {row.product_id: row for row in ProductEmbedding.objects.filter(
        product_id__in=[product.pk for product in products])}
    stale = []
    for product in products:
        content = product_embedding_text(product)
        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()
        row = rows.get(product.pk)
        if not row or row.content_hash != fingerprint or row.model != model or not row.vector:
            stale.append((product, content, fingerprint))

    if stale:
        try:
            vectors = embed_texts([content for _, content, _ in stale], "RETRIEVAL_DOCUMENT")
            for (product, _, fingerprint), vector in zip(stale, vectors):
                row, _ = ProductEmbedding.objects.update_or_create(
                    product=product,
                    defaults={"vector": vector, "content_hash": fingerprint, "model": model},
                )
                rows[product.pk] = row
        except Exception:  # noqa: BLE001 - semantic search degrades to lexical retrieval.
            logger.warning("Không tạo/cập nhật được embedding sản phẩm", exc_info=True)

    return {product_id: row.vector for product_id, row in rows.items()
            if row.model == model and row.vector}
