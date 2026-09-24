"""p3.x: add ticket.ticket_no human-readable business key (add-only, single head)

Adds a race-free, immutable, human-readable ticket number to the P3 ticket table,
mirroring ExecTask/TransferTask ``task_no`` (String(32) unique/not-null/index) and the
``seq_exec_no`` / ``seq_transfer_no`` precedent. Number scheme: ``TK-YYYYMMDD-<seq>``
(<= 32 chars).

Order (arch seq2731 / reviewer seq2730): create sequence -> add nullable column ->
backfill existing rows deterministically -> unique index -> NOT NULL. nextval() is atomic,
so concurrent creators can never collide; the unique index is a backstop. Existing rows
are backfilled from their own creation date and never renumbered; a fresh volume starts
at 1.

Descends from the P3 head ``c9e3f1a2b4d6`` (which itself descends from the P2 close-out)
=> allow-set C (forbidden on the shared live DB); see docs/migration-shared-db-allowlist.md.

Revision ID: e1f2a3b4c5d7
Revises: c9e3f1a2b4d6
Create Date: 2026-09-24 20:35:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d7"
down_revision = "c9e3f1a2b4d6"
branch_labels = None
depends_on = None
# Descends from the P3 head (which descends from the P2 close-out) => forbidden live.
SHARED_LIVE_DB_FORBIDDEN = True


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_ticket_no")
    op.add_column("ticket", sa.Column("ticket_no", sa.String(length=32), nullable=True))
    # Idempotent seed from the current max suffix + 1, mirroring
    # d1e2f3a4b5c6_sequence_backed_no_generation.py. `ticket` is a P3 table and the
    # release/master volume has 0 rows, so this (and the backfill below) is a no-op
    # there; a self-managed DB with pre-existing rows sees the new column all-NULL
    # and therefore seeds to 1.
    op.execute(
        """
        SELECT setval(
            'seq_ticket_no',
            GREATEST(1, COALESCE((
                SELECT MAX(NULLIF(split_part(ticket_no, '-', 3), '')::bigint)
                FROM ticket
            ), 0) + 1),
            false
        )
        """
    )
    # Backfill historical rows deterministically from each row's own created_at
    # (开单日 semantics, arch seq2740①); consumes the sequence so freshly created
    # tickets continue past the backfilled suffix.
    op.execute(
        """
        UPDATE ticket
        SET ticket_no = 'TK-' || to_char(created_at, 'YYYYMMDD') || '-'
                        || lpad(nextval('seq_ticket_no')::text, 3, '0')
        WHERE ticket_no IS NULL
        """
    )
    op.create_index("ix_ticket_ticket_no", "ticket", ["ticket_no"], unique=True)
    op.alter_column("ticket", "ticket_no", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_ticket_ticket_no", table_name="ticket")
    op.drop_column("ticket", "ticket_no")
    op.execute("DROP SEQUENCE IF EXISTS seq_ticket_no")
