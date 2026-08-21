"""stage2 asset contract alignment: asset_host.sensitivity_level

Revision ID: a1c7e9d24b60
Revises: e70f471cb518
Create Date: 2026-08-21 09:05:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'a1c7e9d24b60'
down_revision = 'e70f471cb518'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'asset_host',
        sa.Column('sensitivity_level', sa.String(length=16), nullable=False,
                  server_default='normal'),
    )


def downgrade() -> None:
    op.drop_column('asset_host', 'sensitivity_level')
