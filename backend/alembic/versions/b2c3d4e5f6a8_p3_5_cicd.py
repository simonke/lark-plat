"""p3.5: CI/CD integration — add cicd_provider / release

Provider = a registerable external CI/CD system (gitlab/jenkins/generic) whose
secrets live per-value AES-GCM encrypted in ``config_enc``. ``release`` records
one delivery orchestration and links a REUSED §13 ``workflow_run``
(``trigger_type='release'``); this migration adds tables only.

Add-only; single head descending directly from the P3-4 rev `a1b2c3d4e5f7`
=> allow-set C (forbidden on the shared live DB); see
docs/migration-shared-db-allowlist.md.

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-09-25 17:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "b2c3d4e5f6a8"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None
# Descends from the P3-4 head (which descends from the P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.create_table(
        "cicd_provider",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("config_enc", JSONB(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
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
    )
    op.create_index("ix_cicd_provider_type", "cicd_provider", ["type"])
    op.create_index("ix_cicd_provider_name", "cicd_provider", ["name"])

    op.create_table(
        "release",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.BigInteger(), nullable=False),
        sa.Column("app", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=True),
        sa.Column("artifact_ref", sa.String(length=512), nullable=True),
        sa.Column("env", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("workflow_run_id", sa.BigInteger(), nullable=True),
        sa.Column("target_host_ids", JSONB(), nullable=True),
        sa.Column("rolled_back_from", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["cicd_provider.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_release_provider_id", "release", ["provider_id"])
    op.create_index("ix_release_app", "release", ["app"])
    op.create_index("ix_release_env", "release", ["env"])
    op.create_index("ix_release_status", "release", ["status"])


def downgrade() -> None:
    op.drop_index("ix_release_status", table_name="release")
    op.drop_index("ix_release_env", table_name="release")
    op.drop_index("ix_release_app", table_name="release")
    op.drop_index("ix_release_provider_id", table_name="release")
    op.drop_table("release")
    op.drop_index("ix_cicd_provider_name", table_name="cicd_provider")
    op.drop_index("ix_cicd_provider_type", table_name="cicd_provider")
    op.drop_table("cicd_provider")
