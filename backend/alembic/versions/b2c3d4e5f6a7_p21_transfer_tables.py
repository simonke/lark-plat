"""p2-1: file distribution tables (add-only)

Phase-2 P2-1 frozen contract (2026-09-12):
  file_package      - uploaded file package (name/size manifest/store_path)
  file_item         - file inside a package (rel_path/size/sha256/chunk_size)
  transfer_task     - push/pull distribution task (TF-YYYYMMDD-NNN, state machine)
  transfer_host     - task x host (per-host cursor + verify state machine)
  transfer_log      - append-only per-host transfer log, exec_log-style monthly
                      RANGE partitions (composite PK (id, created_at) so the
                      partition key is covered; UNIQUE (created_at, transfer_host_id, seq))
  seq_transfer_no   - race-free TF task_no generator (B1 contract)

Channels are resolved at dispatch time (AgentChannel default; SshChannel is an
interface placeholder in this batch). All tables are new; a single alembic head
is preserved. ownership/created FKs -> sys_user.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-12 18:00:00.000000
"""
from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_FORWARD_MONTHS = 12


def _month_bounds(part: str) -> tuple[str, str]:
    """Low/next-month bounds for a partition named transfer_log_YYYY_MM."""
    y, m = part.rsplit("_", 2)[1], part.rsplit("_", 1)[1]
    d = date(int(y), int(m), 1)
    nd = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return f"{d:%Y-%m-%d}", f"{nd:%Y-%m-%d}"


def _create_partition(part: str) -> None:
    lo, hi = _month_bounds(part)
    op.execute(f"CREATE TABLE {part} PARTITION OF transfer_log "
               f"FOR VALUES FROM ('{lo}') TO ('{hi}')")


def upgrade() -> None:
    # ── file_package ──────────────────────────────────────────────────────
    op.create_table(
        "file_package",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("store_path", sa.String(length=512), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
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
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_package_name", "file_package", ["name"])

    # ── file_item ─────────────────────────────────────────────────────────
    op.create_table(
        "file_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("package_id", sa.BigInteger(), nullable=False),
        sa.Column("rel_path", sa.String(length=512), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="1048576"),
        sa.ForeignKeyConstraint(["package_id"], ["file_package.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "rel_path"),
    )
    op.create_index("ix_file_item_package_id", "file_item", ["package_id"])

    # ── transfer_task ─────────────────────────────────────────────────────
    op.create_table(
        "transfer_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_no", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("package_id", sa.BigInteger(), nullable=True),
        sa.Column("source_host_id", sa.BigInteger(), nullable=True),
        sa.Column("source_host_path", sa.String(length=512), nullable=True),
        sa.Column("target_path", sa.String(length=512), nullable=False),
        sa.Column("host_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("overwrite", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verify", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("limit_mbps", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="processing"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["package_id"], ["file_package.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_no"),
    )
    op.create_index("ix_transfer_task_task_no", "transfer_task", ["task_no"])
    op.create_index("ix_transfer_task_package_id", "transfer_task", ["package_id"])
    op.create_index("ix_transfer_task_status", "transfer_task", ["status"])
    op.create_index("ix_transfer_task_created_by", "transfer_task", ["created_by"])

    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_transfer_no")

    # ── transfer_host ─────────────────────────────────────────────────────
    op.create_table(
        "transfer_host",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("transfer_task_id", sa.BigInteger(), nullable=False),
        sa.Column("host_id", sa.BigInteger(), nullable=False),
        sa.Column("hostname", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("ip", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="agent"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("current_offset", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("verify_sha256", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["transfer_task_id"], ["transfer_task.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transfer_task_id", "host_id"),
    )
    op.create_index("ix_transfer_host_transfer_task_id", "transfer_host", ["transfer_task_id"])
    op.create_index("ix_transfer_host_host_id", "transfer_host", ["host_id"])
    op.create_index("ix_transfer_host_status", "transfer_host", ["status"])

    # ── transfer_log (exec_log partition pattern) ─────────────────────────
    op.execute(
        """
        CREATE TABLE transfer_log (
            id BIGINT NOT NULL,
            transfer_host_id BIGINT NOT NULL,
            seq INTEGER NOT NULL,
            level VARCHAR(16) NOT NULL DEFAULT 'info',
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT transfer_log_pkey PRIMARY KEY (id, created_at),
            CONSTRAINT uq_transfer_log_created_at_transfer_host_id_seq
                UNIQUE (created_at, transfer_host_id, seq),
            CONSTRAINT fk_transfer_log_transfer_host FOREIGN KEY (transfer_host_id)
                REFERENCES transfer_host (id) ON DELETE CASCADE
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute("CREATE TABLE transfer_log_default PARTITION OF transfer_log DEFAULT")
    first = op.get_bind().execute(
        sa.text("SELECT date_trunc('month', now())::date")
    ).scalar()
    for i in range(_FORWARD_MONTHS + 1):
        part = (first + timedelta(days=31 * i)).strftime("transfer_log_%Y_%m")
        _create_partition(part)

    op.execute("CREATE INDEX ix_transfer_log_transfer_host_id ON transfer_log (transfer_host_id)")
    op.execute("CREATE INDEX ix_transfer_log_created_at ON transfer_log (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS transfer_log CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS seq_transfer_no")
    op.drop_table("transfer_host")
    op.drop_table("transfer_task")
    op.drop_table("file_item")
    op.drop_table("file_package")