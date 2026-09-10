"""add mon_rule scope/level/converge/escalate_levels columns

Revision ID: a1b2c3d4e5f6
Revises: e6f7a8b9c0d1
Create Date: 2026-09-09

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scope (US-03: server-side entity filtering)
    op.add_column("mon_rule", sa.Column("scope_type", sa.String(length=16), nullable=True))
    op.add_column("mon_rule", sa.Column("scope_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # severity level for alerts created by this rule
    op.add_column("mon_rule", sa.Column("level", sa.String(length=16), nullable=False, server_default="warning"))

    # convergence dedup window
    op.add_column("mon_rule", sa.Column("converge_sec", sa.Integer(), nullable=False, server_default="0"))

    # escalation levels list
    op.add_column("mon_rule", sa.Column("escalate_levels", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("mon_rule", "escalate_levels")
    op.drop_column("mon_rule", "converge_sec")
    op.drop_column("mon_rule", "level")
    op.drop_column("mon_rule", "scope_ids")
    op.drop_column("mon_rule", "scope_type")
