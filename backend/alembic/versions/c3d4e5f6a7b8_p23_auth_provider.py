"""p2-3: identity integration (LDAP / OAuth2) - add-only

Frozen contract: api-design-v3 §3 + architecture-phase23 §5.
  auth_provider       - external identity provider (type=ldap|oauth2, code is the
                        routing key for /auth/oauth/{provider}/*, config_enc
                        AES-GCM encoded like notify_channel.config_enc)
  sys_user.auth_source         - 'local' (default) | 'ldap' | 'oauth2'
  sys_user.external_id         - IdP subject/uid for external users
  sys_user.last_external_login_at

Additive migration: existing rows default to 'local'; a single alembic head is
preserved by chaining onto the P2-MA head d4e5f6a7b8c9 (P2-3-B seq1845):
b2c3d4e5f6a7 -> d4e5f6a7b8c9 -> c3d4e5f6a7b8.

Revision ID: c3d4e5f6a7b8
Revises: d4e5f6a7b8c9
Create Date: 2026-09-17 23:45:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_provider",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("config_enc", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_auth_provider_code", "auth_provider", ["code"])

    op.add_column(
        "sys_user",
        sa.Column("auth_source", sa.String(length=16), nullable=False, server_default="local"),
    )
    op.add_column("sys_user", sa.Column("external_id", sa.String(length=128), nullable=True))
    op.add_column(
        "sys_user",
        sa.Column("last_external_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sys_user", "last_external_login_at")
    op.drop_column("sys_user", "external_id")
    op.drop_column("sys_user", "auth_source")
    op.drop_index("ix_auth_provider_code", table_name="auth_provider")
    op.drop_table("auth_provider")
