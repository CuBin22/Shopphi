# Chatbot Product Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Shopphi product retrieval with Gemini semantic embeddings while retaining keyword fallback and live product facts.

**Architecture:** Cache each product document embedding and a content fingerprint in PostgreSQL JSONField. Embed the user query with Gemini, combine cosine similarity with lexical relevance, and pass only the top product contexts to the existing Gemini answer call. Re-embed changed/missing documents lazily; fall back to keyword retrieval when keys or embedding calls are unavailable.

**Tech Stack:** Django ORM/PostgreSQL, Python standard-library HTTP, Gemini `embedContent` API using `gemini-embedding-001` and 768 dimensions.

**Spec:** `docs/superpowers/specs/2026-10-31-chatbot-product-embeddings-design.md`

## Global Constraints

- Keep Gemini keys server-side in `.env`; never log or return them.
- Keep current price, stock, and order facts sourced from PostgreSQL.
- Do not add pgvector or another package.
- Preserve lexical retrieval when embedding is unavailable.

## Review Focus

- Missing/invalid Gemini key: retrieval remains usable through lexical fallback.
- Gemini embedding HTTP or malformed response: do not fail the chatbot request.
- Product text changes: stale vector must be refreshed before semantic ranking.
- Empty or zero-norm vectors: cosine calculation must not divide by zero.
- Similar but weak matches: keep the existing result limit and relevance threshold.

---

### Task 1: Persist product vectors

**Files:** `chatbot/models.py`, new `chatbot/migrations/0002_productembedding.py`

**Interfaces:** Add `ProductEmbedding` with one-to-one `product`, JSON vector, `content_hash`, `model`, and updated timestamp.

- [ ] Define the model and generate its migration.
- [ ] Run `python manage.py check` and `python manage.py makemigrations --check --dry-run`.

### Task 2: Gemini embedding and ranking

**Files:** new `chatbot/embeddings.py`, `chatbot/service.py`

**Interfaces:** `embed_text(text, task_type) -> list[float]`, `cosine_similarity(left, right) -> float`, and `product_embedding_text(product) -> str`.

- [ ] Implement secure REST calls to Gemini `embedContent` with `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` task types.
- [ ] Cache or refresh vectors when the product document fingerprint changes.
- [ ] Rank with semantic similarity plus current lexical score; preserve top-3 and lexical fallback.
- [ ] Keep product price and stock out of embeddings and use current database context for answer generation.

### Task 3: Configuration and operating notes

**Files:** `.env.example`, `Shopphi/settings.py`, `README.md`

- [ ] Add `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`.
- [ ] Document that the Gemini key enables both generation and embeddings and that embeddings are cached in PostgreSQL.
- [ ] Rebuild the Docker web service, run Django system check, and check the diff for whitespace errors.
