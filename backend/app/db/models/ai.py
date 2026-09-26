"""AIOps models (P4 E3/E7/E8): kb_embedding, ai_action, ai_eval_case, ai_eval_run.

ADR#2 (b): same-PG, application-side cosine — ``kb_embedding.embedding`` is a
plain JSONB float array (NO pgvector extension / dependency). ADR#3: the
``entity_scope`` list is the retrieval-layer visibility key; queries carry the
scope as an input (never a post-filter).

E7 ``ai_action`` and E1 ``ops_event`` are append-only (no ``updated_at``).

Frozen contract: @架构 P4 tuple v1 (seq3203) + seq3212; §12.5 same-table reuse.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# E7 governance vocabulary.
AI_ACTION_DECISIONS = ("adopted", "rejected", "auto", "dry_run")

# P6 (E6) risk vocabulary for automated remediation (lowercase, single source).
# Governed DB validation source: `risk_level not in RISK_LEVELS => reject`.
RISK_LEVELS = ("low", "medium", "high")

# E8 eval case kinds.
AI_EVAL_CASE_KINDS = ("case", "negative_control")


class KbEmbedding(Base):
    """One embedded KB chunk, scoped to the entity ids allowed to retrieve it."""

    __tablename__ = "kb_embedding"
    __table_args__ = (
        Index("ix_kb_embedding_doc_ref", "doc_ref"),
        Index("ix_kb_embedding_chunk_ref", "chunk_ref"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    # Application-side vector: JSONB list[float] (ADR#2 (b), no pgvector).
    embedding: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Retrieval-layer visibility key: list[str] of entity ids (NOT NULL, fail-closed).
    # A missing/empty scope matches NO non-empty caller scope (never NULL=global).
    entity_scope: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AiAction(Base):
    """Append-only AI action/decision log (E7 governance)."""

    __tablename__ = "ai_action"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis_refs: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    # P6 (E6) governance add-only columns. Plain String + comment enum, never a
    # CHECK/Enum referencing the services-layer APPROVAL_MODES (avoids a
    # models -> services reverse dependency; same shape as `decision`).
    approval_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)  # auto_policy|manual
    policy_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rollback_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AiEvalCase(Base):
    """One offline eval case (E8); ``is_neg_control`` cases must stay red-able."""

    __tablename__ = "ai_eval_case"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    expected: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_neg_control: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AiEvalRun(Base):
    """One eval execution result row (E8)."""

    __tablename__ = "ai_eval_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
