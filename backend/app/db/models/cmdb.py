"""CMDB relation model (P3-3): `entity_relation`.

Single relation truth source, shared with the §26 AIOps topology (same-table
reuse = **YES**): AIOps consumes `entity_relation` and only extends the
`*_type` / `rel_type` vocabularies — it must NOT create a second
`cmdb_ci_relation` table. A directed CI edge `src --rel_type--> dst`, deduped by
the UNIQUE 5-tuple, with a 禁自环 CHECK and three lookup indexes.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Endpoint node types (P3-3 tuple v0.4: host | host_group). §26 AIOps may extend.
ENTITY_TYPES = ("host", "host_group")

# Initial rel_type vocabulary (tuple v0.2). §26 AIOps may extend.
REL_TYPES = ("depends_on", "runs_on", "connects_to", "member_of", "hosts")


class EntityRelation(Base, TimestampMixin):
    """Directed CI edge; UNIQUE(src_type,src_id,dst_type,dst_id,rel_type) dedups."""

    __tablename__ = "entity_relation"
    __table_args__ = (
        UniqueConstraint(
            "src_type", "src_id", "dst_type", "dst_id", "rel_type",
            name="uq_entity_relation_edge",
        ),
        CheckConstraint(
            "NOT (src_type = dst_type AND src_id = dst_id)",
            name="ck_entity_relation_no_self_loop",
        ),
        Index("ix_entity_relation_src", "src_type", "src_id"),
        Index("ix_entity_relation_dst", "dst_type", "dst_id"),
        Index("ix_entity_relation_rel_type", "rel_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    src_type: Mapped[str] = mapped_column(String(32), nullable=False)
    src_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dst_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dst_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rel_type: Mapped[str] = mapped_column(String(32), nullable=False)
    properties: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    remark: Mapped[str] = mapped_column(String(256), default="")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
