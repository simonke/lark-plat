"""p3.4: 编排 Playbook — add workflow / workflow_version / workflow_run / workflow_node_run

Playbook = versioned DAG. ``workflow`` holds the ``current_version`` pointer,
``workflow_version`` is append-only (UNIQUE(workflow_id, version)), and
``workflow_run``/``workflow_node_run`` record execution state
(UNIQUE(run_id, node_key)). Node types reuse the一期 exec_task / approval
primitives; this migration adds tables only.

Add-only; single head descending directly from the P3-3 head `f2a3b4c5d6e7`
=> allow-set C (forbidden on the shared live DB); see
docs/migration-shared-db-allowlist.md.

Revision ID: a1b2c3d4e5f7
Revises: f2a3b4c5d6e7
Create Date: 2026-09-25 11:40:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f7"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None
# Descends from the P3-3 head (which descends from the P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.create_table(
        "workflow",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
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
    op.create_index("ix_workflow_name", "workflow", ["name"], unique=True)

    op.create_table(
        "workflow_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", JSONB(), nullable=False),
        sa.Column("editor_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),
    )
    op.create_index("ix_workflow_version_workflow_id", "workflow_version", ["workflow_id"])

    op.create_table(
        "workflow_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("workflow_id", sa.BigInteger(), nullable=False),
        sa.Column("workflow_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("trigger_type", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("trigger_ref", JSONB(), nullable=True),
        sa.Column("context", JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_run_workflow_id", "workflow_run", ["workflow_id"])
    op.create_index("ix_workflow_run_status", "workflow_run", ["status"])

    op.create_table(
        "workflow_node_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("exec_task_id", sa.BigInteger(), nullable=True),
        sa.Column("approval_id", sa.BigInteger(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output", JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["workflow_run.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "node_key", name="uq_workflow_node_run"),
    )
    op.create_index("ix_workflow_node_run_run_id", "workflow_node_run", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_node_run_run_id", table_name="workflow_node_run")
    op.drop_table("workflow_node_run")
    op.drop_index("ix_workflow_run_status", table_name="workflow_run")
    op.drop_index("ix_workflow_run_workflow_id", table_name="workflow_run")
    op.drop_table("workflow_run")
    op.drop_index("ix_workflow_version_workflow_id", table_name="workflow_version")
    op.drop_table("workflow_version")
    op.drop_index("ix_workflow_name", table_name="workflow")
    op.drop_table("workflow")
