"""p5: AIOps E3/E4/E5 — workflow.kind + ops_event(entity,action,ts) index

E4 RCA is read-time aggregation over `ops_event` (NO new table); E5 playbook
REUSES the P3-4 workflow engine (a playbook is a `workflow` row with
`kind='playbook'`, NO new table / NO second executor). This migration only adds
the `workflow.kind` discriminator and the `ix_ops_event_entity_action_ts` index.

Add-only; single head descending directly from the P4 rev `e9d8c7b6a5f4`
=> allow-set C (forbidden on the shared live DB); see
docs/migration-shared-db-allowlist.md.

Revision ID: f5a6b7c8d9e0
Revises: e9d8c7b6a5f4
Create Date: 2026-09-25 22:50:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e9d8c7b6a5f4"
branch_labels = None
depends_on = None
# Descends from the P4 head (which descends from the P3-5/P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.add_column(
        "workflow",
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
            server_default="workflow",
        ),
    )
    op.create_index(
        "ix_ops_event_entity_action_ts",
        "ops_event",
        ["entity_type", "entity_id", "action", "ts"],
    )


def downgrade() -> None:
    op.drop_index("ix_ops_event_entity_action_ts", table_name="ops_event")
    op.drop_column("workflow", "kind")
