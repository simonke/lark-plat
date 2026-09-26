"""p6: AIOps E6 controlled auto-remediation (L4) — governed automation tables.

Add-only, single head descending directly from the P5 rev `f5a6b7c8d9e0`
=> allow-set C (forbidden on the shared live DB).

Four NEW tables: `remediation_policy` / `automation_whitelist` / `automation_level`
/ `circuit_breaker_state`. `remediation_run` is deliberately NOT created — a
remediation run is an existing `workflow_run`. `ai_action`/`approval_request` gain
add-only plain-String columns (no CHECK/Enum; no models -> services reverse dep).

Revision ID: P6_REV
Revises: f5a6b7c8d9e0
Create Date: 2026-09-26 18:30:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "P6_REV"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None
# Descends from the P5 head (which descends from P4/P3/P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "remediation_policy",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("asset_class", sa.String(length=64), nullable=False),
        sa.Column("op_type", sa.String(length=64), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("whitelist_ref", sa.String(length=128), nullable=True),
        sa.Column("verification_ref", sa.String(length=128), nullable=True),
        sa.Column("circuit_threshold", sa.Integer(), nullable=True),
        sa.Column("rollback_window", sa.Integer(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "automation_whitelist",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_automation_whitelist_action", "automation_whitelist", ["action"])
    op.create_table(
        "automation_level",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("level", sa.String(length=16), nullable=False, unique=True),
        sa.Column("capability", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
    )
    op.create_table(
        "circuit_breaker_state",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=64), nullable=False, unique=True),
        sa.Column("state", sa.String(length=16), server_default="closed", nullable=False),
        sa.Column("current", sa.Integer(), server_default="0", nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=True),
        sa.Column("last_tripped_at", _TS, nullable=True),
        sa.Column("created_at", _TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("now()"), nullable=False),
    )

    op.add_column("ai_action", sa.Column("approval_mode", sa.String(length=16), nullable=True))
    op.add_column("ai_action", sa.Column("policy_ref", sa.String(length=128), nullable=True))
    op.add_column("ai_action", sa.Column("verification_ref", sa.String(length=128), nullable=True))
    op.add_column("ai_action", sa.Column("rollback_ref", sa.String(length=128), nullable=True))

    op.add_column(
        "approval_request",
        sa.Column("approval_mode", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.add_column("approval_request", sa.Column("policy_ref", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("approval_request", "policy_ref")
    op.drop_column("approval_request", "approval_mode")
    op.drop_column("ai_action", "rollback_ref")
    op.drop_column("ai_action", "verification_ref")
    op.drop_column("ai_action", "policy_ref")
    op.drop_column("ai_action", "approval_mode")
    op.drop_table("circuit_breaker_state")
    op.drop_table("automation_level")
    op.drop_index("ix_automation_whitelist_action", table_name="automation_whitelist")
    op.drop_table("automation_whitelist")
    op.drop_table("remediation_policy")
