"""p4: AIOps kernel — add ops_event / kb_embedding / ai_action / ai_eval_case / ai_eval_run

E1 unified ops event (append-only, single write seam), E3 KB RAG store (ADR#2 (b):
same-PG application-side cosine — plain JSONB vector, NO pgvector extension), E7
AI governance action log (append-only), E8 offline eval case/run tables.

Add-only; single head descending directly from the P3-5 rev `b2c3d4e5f6a8`
=> allow-set C (forbidden on the shared live DB); see
docs/migration-shared-db-allowlist.md.

Revision ID: e9d8c7b6a5f4
Revises: b2c3d4e5f6a8
Create Date: 2026-09-25 20:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "e9d8c7b6a5f4"
down_revision = "b2c3d4e5f6a8"
branch_labels = None
depends_on = None
# Descends from the P3-5 head (which descends from the P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.create_table(
        "ops_event",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("refs", JSONB(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ops_event_source_ts", "ops_event", ["source", "ts"])
    op.create_index("ix_ops_event_entity_ts", "ops_event", ["entity_type", "entity_id", "ts"])
    op.create_index(
        "ix_ops_event_refs_gin", "ops_event", ["refs"], postgresql_using="gin",
    )

    op.create_table(
        "kb_embedding",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("doc_ref", sa.String(length=64), nullable=False),
        sa.Column("chunk_ref", sa.String(length=128), nullable=False),
        sa.Column("embedding", JSONB(), nullable=False),
        sa.Column("entity_scope", JSONB(), nullable=True),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_embedding_doc_ref", "kb_embedding", ["doc_ref"])
    op.create_index("ix_kb_embedding_chunk_ref", "kb_embedding", ["chunk_ref"])

    op.create_table(
        "ai_action",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("input_snapshot", JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("basis_refs", JSONB(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("actor", sa.BigInteger(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_eval_case",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("input", JSONB(), nullable=True),
        sa.Column("expected", JSONB(), nullable=True),
        sa.Column("is_neg_control", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_eval_case_name", "ai_eval_case", ["name"])

    op.create_table(
        "ai_eval_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("case_id", sa.BigInteger(), nullable=True),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("actual", JSONB(), nullable=True),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report", JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_eval_run")
    op.drop_index("ix_ai_eval_case_name", table_name="ai_eval_case")
    op.drop_table("ai_eval_case")
    op.drop_table("ai_action")
    op.drop_index("ix_kb_embedding_chunk_ref", table_name="kb_embedding")
    op.drop_index("ix_kb_embedding_doc_ref", table_name="kb_embedding")
    op.drop_table("kb_embedding")
    op.drop_index("ix_ops_event_refs_gin", table_name="ops_event")
    op.drop_index("ix_ops_event_entity_ts", table_name="ops_event")
    op.drop_index("ix_ops_event_source_ts", table_name="ops_event")
    op.drop_table("ops_event")
