"""E3 KB ingestion seam (P5): published article -> chunk -> embed -> store.

`ingest_article(db, article, version)` is the single write seam that forwards a
KB article's current version into the vector store. It participates in the
**caller's transaction** (it never commits): the chunk rows and the business
change land atomically, so a failed publish never leaves orphan embeddings.

Re-ingesting the same article is an idempotent REPLACE: the previous chunks for
that `doc_ref` are deleted before the new ones are upserted, so an edit/rollback
never duplicates chunks or leaves stale vectors behind.

Frozen contract: @架构 P5 tuple v1->r2 (seq3332) + @需求 §29.1.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import KbEmbedding
from app.services.ai_scope import GLOBAL_SCOPE_TOKEN
from app.services.embedding_store import build_embedding_store
from app.services.llm_client import EchoLLMClient, LLMClient

logger = logging.getLogger(__name__)

# Chunk width (characters) for the deterministic offline chunker; a real
# tokenizer is an add-only subclass, the seam (doc_ref/chunk_ref) stays frozen.
DEFAULT_CHUNK_SIZE = 512

# Cost/limit guard (P5.1 ④): bound the number of chunks embedded per publish so a
# pathological document cannot fan out into an unbounded embed call. Over-cap is a
# GRACEFUL degradation — the first `_MAX_EMBED_CHUNKS` chunks are embedded, the rest
# are skipped with a WARNING audit line, and the publish still succeeds (no raise,
# no new error code). Within-cap behaviour is unchanged.
_MAX_EMBED_CHUNKS = 200


def _client() -> LLMClient:
    return EchoLLMClient()


def _chunk_text(text: str, size: int) -> list[str]:
    text = text or ""
    if not text:
        return []
    size = max(1, int(size))
    return [text[i:i + size] for i in range(0, len(text), size)]


def _entity_scope(article) -> list[str]:
    """Retrieval-layer visibility key (ADR#3): the exact ids this doc is scoped to.

    A `public` article additionally carries the explicit `GLOBAL_SCOPE_TOKEN`
    wildcard (every actor's kb scope includes it); otherwise only the article id.
    """
    scope = {str(article.id)}
    if getattr(article, "visibility", "") == "public":
        scope.add(GLOBAL_SCOPE_TOKEN)
    return sorted(scope)


def ingest_article(
    db: Session,
    article,
    version=None,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> int:
    """Embed + upsert one article's current version in the caller's transaction.

    Returns the number of chunks written. Empty content is a valid no-op (any
    prior chunks for this `doc_ref` are still replaced away). Never commits.
    """
    content = getattr(version, "content", None)
    if content is None:
        content = getattr(article, "summary", "") or ""
    doc_ref = str(article.id)

    # Idempotent replace seam: drop this doc's prior chunks first (same tx).
    db.query(KbEmbedding).filter(KbEmbedding.doc_ref == doc_ref).delete(
        synchronize_session=False
    )

    chunks = _chunk_text(content, chunk_size)
    if not chunks:
        return 0
    if len(chunks) > _MAX_EMBED_CHUNKS:
        skipped = len(chunks) - _MAX_EMBED_CHUNKS
        logger.warning(
            "kb_ingestion: doc_ref=%s produced %d chunks > cap %d; embedding first %d, "
            "skipping %d (graceful degradation, publish still succeeds)",
            doc_ref,
            len(chunks),
            _MAX_EMBED_CHUNKS,
            _MAX_EMBED_CHUNKS,
            skipped,
        )
        chunks = chunks[:_MAX_EMBED_CHUNKS]
    vectors = _client().embed(chunks)
    scope = _entity_scope(article)
    records = [
        {
            "doc_ref": doc_ref,
            "chunk_ref": f"article:{doc_ref}:{idx}",
            "embedding": vec,
            "entity_scope": scope,
            "dim": len(vec),
        }
        for idx, vec in enumerate(vectors)
    ]
    return build_embedding_store(db).upsert(records)
