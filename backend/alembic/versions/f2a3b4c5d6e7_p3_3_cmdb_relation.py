"""p3.3: CMDB 深化 — add `entity_relation` (relations / topology / impact)

Creates the ONE relation truth source `entity_relation` (same-table reuse = YES;
§26 AIOps reuses this table — no second `cmdb_ci_relation`). A directed CI edge
`src --rel_type--> dst` with a UNIQUE 5-tuple dedup, a 禁自环 CHECK
`NOT(src_type=dst_type AND src_id=dst_id)`, and three lookup indexes.

Add-only; single head descending directly from the P3.x head `e1f2a3b4c5d7`
=> allow-set C (forbidden on the shared live DB); see
docs/migration-shared-db-allowlist.md.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d7
Create Date: 2026-09-24 23:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d7"
branch_labels = None
depends_on = None
# Descends from the P3.x head (which descends from the P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.create_table(
        "entity_relation",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("src_type", sa.String(length=32), nullable=False),
        sa.Column("src_id", sa.BigInteger(), nullable=False),
        sa.Column("dst_type", sa.String(length=32), nullable=False),
        sa.Column("dst_id", sa.BigInteger(), nullable=False),
        sa.Column("rel_type", sa.String(length=32), nullable=False),
        sa.Column("properties", JSONB(), nullable=True),
        sa.Column("remark", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "src_type", "src_id", "dst_type", "dst_id", "rel_type",
            name="uq_entity_relation_edge",
        ),
        sa.CheckConstraint(
            "NOT (src_type = dst_type AND src_id = dst_id)",
            name="ck_entity_relation_no_self_loop",
        ),
    )
    op.create_index("ix_entity_relation_src", "entity_relation", ["src_type", "src_id"])
    op.create_index("ix_entity_relation_dst", "entity_relation", ["dst_type", "dst_id"])
    op.create_index("ix_entity_relation_rel_type", "entity_relation", ["rel_type"])


def downgrade() -> None:
    op.drop_index("ix_entity_relation_rel_type", table_name="entity_relation")
    op.drop_index("ix_entity_relation_dst", table_name="entity_relation")
    op.drop_index("ix_entity_relation_src", table_name="entity_relation")
    op.drop_table("entity_relation")
