"""Embedding store (P4 ADR#2 (b) + ADR#3): application-side cosine, scoped retrieval.

ADR#2 (b): vectors live in the same PG as a JSONB float array — NO pgvector
extension/dependency. Cosine similarity is computed in the application.

ADR#3 (US-03): `scope` is a *query input*, never a post-filter. The public
`query()` forwards `scope` into `_candidates()`, which is the single retrieval
seam both implementations must honour:
  - `InMemoryEmbeddingStore._candidates` filters candidates by `scope` (unit);
  - `PostgresArrayEmbeddingStore._candidates` pushes an `entity_scope` predicate
    into SQL (production / live-F).
A record physically present but out of scope must never be returned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models.ai import KbEmbedding

# Named config symbol + enum values (E8/ADR#2 store selection; @架构 seq3230).
EMBEDDING_STORE_CONFIG_KEY = "ai.embedding_store"
EMBEDDING_STORE_PG_ARRAY = "pg_array"
EMBEDDING_STORE_IN_MEMORY = "in_memory"


@dataclass
class ScopeFilter:
    """The caller's retrieval scope: which entity ids may be returned (ADR#3).

    An unknown/undefined ``entity_type`` yields an empty ``entity_ids`` set, and an
    empty scope is **fail-closed** (nothing is retrieved).
    """

    entity_type: str
    entity_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass
class EmbeddingHit:
    """One retrieved chunk (non-authoritative; caller decides authority)."""

    doc_ref: str
    chunk_ref: str
    score: float
    dim: int


def _overlaps(record_scope, scope: ScopeFilter | None) -> bool:
    """Retrieval-layer visibility: NULL scope = global; empty caller scope = closed."""
    if scope is None:
        return True
    if not scope.entity_ids:
        return False  # fail-closed: no visible entities => nothing retrievable
    if record_scope is None:
        return True  # global record is visible to any non-empty scope
    if isinstance(record_scope, (list, tuple, set, frozenset)):
        rec = {str(x) for x in record_scope}
    else:  # scalar id (e.g. entity_scope=7)
        rec = {str(record_scope)}
    return bool(rec & {str(i) for i in scope.entity_ids})


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(float(a[i]) * float(b[i]) for i in range(n))
    na = math.sqrt(sum(float(x) * float(x) for x in a[:n])) or 1.0
    nb = math.sqrt(sum(float(x) * float(x) for x in b[:n])) or 1.0
    return dot / (na * nb)


class EmbeddingStore:
    """Retrieval-store interface; `_candidates` is the single scope seam (ADR#3)."""

    def upsert(self, records: list[dict]) -> int:
        raise NotImplementedError

    def query(
        self, query_vector: list[float], *, scope: ScopeFilter | None = None, limit: int = 10
    ) -> list[EmbeddingHit]:
        candidates = self._candidates(query_vector=query_vector, scope=scope, limit=limit)
        ordered = sorted(candidates, key=lambda h: h.score, reverse=True)
        return ordered[:limit]

    def _candidates(
        self, *, query_vector: list[float], scope: ScopeFilter | None = None, limit: int = 10
    ) -> list[EmbeddingHit]:
        raise NotImplementedError


class InMemoryEmbeddingStore(EmbeddingStore):
    """Offline store for unit/lock runs (no DB)."""

    def __init__(self, records: list[dict] | None = None):
        # record: {doc_ref, chunk_ref, embedding, entity_scope, dim}
        self._rows: list[dict] = [dict(r) for r in (records or [])]

    def upsert(self, records: list[dict]) -> int:
        self._rows.extend(dict(r) for r in (records or []))
        return len(records or [])

    def _candidates(
        self, *, query_vector: list[float], scope: ScopeFilter | None = None, limit: int = 10
    ) -> list[EmbeddingHit]:
        hits: list[EmbeddingHit] = []
        for row in self._rows:
            if not _overlaps(row.get("entity_scope"), scope):
                continue
            hits.append(
                EmbeddingHit(
                    doc_ref=str(row.get("doc_ref", "")),
                    chunk_ref=str(row.get("chunk_ref", "")),
                    score=_cosine(query_vector, row.get("embedding") or []),
                    dim=int(row.get("dim") or len(row.get("embedding") or [])),
                )
            )
        return sorted(hits, key=lambda h: h.score, reverse=True)[:limit]


class PostgresArrayEmbeddingStore(EmbeddingStore):
    """Production / live-F store: scoped SQL candidate fetch + application cosine.

    A session may be injected directly (``db=``) or lazily via ``session_factory``
    (used by the offline structural lock to observe the compiled query).
    """

    def __init__(self, db: Session | None = None, session_factory=None):
        self.db = db
        self._session_factory = session_factory

    def _session(self) -> tuple[Session, bool]:
        if self.db is not None:
            return self.db, False
        if self._session_factory is not None:
            return self._session_factory(), True
        raise RuntimeError("PostgresArrayEmbeddingStore requires a session/session_factory")

    def upsert(self, records: list[dict]) -> int:
        session, owned = self._session()
        try:
            count = 0
            for row in records or []:
                session.add(
                    KbEmbedding(
                        doc_ref=str(row.get("doc_ref", "")),
                        chunk_ref=str(row.get("chunk_ref", "")),
                        embedding=list(row.get("embedding") or []),
                        entity_scope=list(row["entity_scope"]) if row.get("entity_scope") else None,
                        dim=int(row.get("dim") or len(row.get("embedding") or [])),
                    )
                )
                count += 1
            session.flush()
            return count
        finally:
            if owned:
                session.close()

    def _candidates(
        self, *, query_vector: list[float], scope: ScopeFilter | None = None, limit: int = 10
    ) -> list[EmbeddingHit]:
        session, owned = self._session()
        try:
            stmt = select(
                KbEmbedding.doc_ref,
                KbEmbedding.chunk_ref,
                KbEmbedding.embedding,
                KbEmbedding.dim,
            )
            if scope is not None:
                if not scope.entity_ids:
                    return []  # fail-closed: no visible entities => nothing retrievable
                ids = [str(i) for i in scope.entity_ids]
                # Query-layer scope predicate (ADR#3): correlated EXISTS over the
                # JSONB array; compiled SQL carries `entity_scope ... IN (...)`.
                elem = func.jsonb_array_elements_text(KbEmbedding.entity_scope).table_valued("value")
                overlap = select(1).select_from(elem).where(elem.c.value.in_(ids)).exists()
                stmt = stmt.where(or_(KbEmbedding.entity_scope.is_(None), overlap))
            hits: list[EmbeddingHit] = []
            for doc_ref, chunk_ref, embedding, dim in session.execute(stmt).all():
                hits.append(
                    EmbeddingHit(
                        doc_ref=str(doc_ref),
                        chunk_ref=str(chunk_ref),
                        score=_cosine(query_vector, list(embedding or [])),
                        dim=int(dim or 0),
                    )
                )
            return sorted(hits, key=lambda h: h.score, reverse=True)[:limit]
        finally:
            if owned:
                session.close()
