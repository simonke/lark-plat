"""Unified ops-event model (P4 E1): `ops_event`, append-only.

Single write seam: every row is produced by ``event_service.emit(db, ...)``; no
other service constructs ``OpsEvent`` (enforced by a static grep lock). Rows are
append-only (no ``updated_at``) and forward-only (no backfill).

Frozen contract: @架构 P4 tuple v1 (seq3203) + 勘误#1 (seq3207) + seq3212.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Tuple D: unified event source vocabulary.
OPS_EVENT_SOURCES = ("monitor", "exec", "audit", "ticket", "kb")


class OpsEvent(Base):
    """One normalized operations event (append-only; single-write seam)."""

    __tablename__ = "ops_event"
    __table_args__ = (
        Index("ix_ops_event_source_ts", "source", "ts"),
        Index("ix_ops_event_entity_ts", "entity_type", "entity_id", "ts"),
        # P5 E4 (tuple v1->r2 seq3332): entity+action timeline index for RCA aggregation.
        Index(
            "ix_ops_event_entity_action_ts",
            "entity_type", "entity_id", "action", "ts",
        ),
        # GIN only takes effect on PostgreSQL; other dialects (e.g. sqlite locks)
        # ignore the dialect kwarg and create a plain index.
        Index("ix_ops_event_refs_gin", "refs", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # entity ids are string-typed across the platform (host ip ∪ hostname ∪ str(id));
    # see HostRepository.visible_entity_ids.
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    refs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
