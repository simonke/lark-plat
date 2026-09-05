"""widen terminal_session.status for awaiting_approval (17 chars)

E2E validation against PostgreSQL surfaced StringDataRightTruncation: the
sensitive-host approval flow persists status='awaiting_approval' (17 chars)
into a varchar(16) column, crashing with a generic 500. SQLite unit tests do
not enforce column width, so the bug only manifests against the real schema.

Revision ID: a7b3c5d9f2e1
Revises: c4f7a1d20e91
Create Date: 2026-09-05 10:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'a7b3c5d9f2e1'
down_revision = 'c4f7a1d20e91'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'terminal_session',
        'status',
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'terminal_session',
        'status',
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )