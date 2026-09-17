"""p2-ma fix: add mon_alert.last_event_at (freshness basis, H2) - add-only

Ruling H2 (seq1780/1786): the sweep's metric-freshness check keys off the last
event that touched an alert, not `updated_at`. Additive nullable column; a single
alembic head is preserved by chaining onto b2c3d4e5f6a7.

NOTE: P2-3's c3d4e5f6a7b8 migration also chains onto b2c3d4e5f6a7. That branch is
not merged; when it lands it must re-chain onto d4e5f6a7b8c9 to keep a single head.

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-09-17 23:58:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mon_alert",
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "mon_alert",
        sa.Column("pending_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mon_alert", "pending_since")
    op.drop_column("mon_alert", "last_event_at")
