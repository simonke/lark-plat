"""sequence-backed task_no / approval_no generation (B1, P2)

Replaces the max(id)+1 window reads in exec_service._task_no / _approval_no and
approval_service._approval_no with a shared PostgreSQL sequence per number.
nextval() is atomic across concurrent creators, so two requests created at the
same time can no longer collide on the same display number (unique constraint
retained as a backstop).

Number scheme stays as the display layer derives it:
  - exec:      YYYYMMDD-<seq>       (length <= 32)
  - approval:  AP-YYYYMMDD-<seq>    (length <= 32)
The sequence is seeded once, idempotently, from the current maximum suffix + 1,
so existing rows are never renumbered and a fresh volume starts at 1.

Revision ID: d1e2f3a4b5c6
Revises: a7b3c5d9f2e1
Create Date: 2026-09-05 10:00:00.000000
"""
from __future__ import annotations

from alembic import op

revision = 'd1e2f3a4b5c6'
down_revision = 'a7b3c5d9f2e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_exec_no")
    op.execute("CREATE SEQUENCE IF NOT EXISTS seq_approval_no")
    # Seed from existing data (idempotent): next nextval() == max_suffix + 1.
    op.execute(
        """
        SELECT setval(
            'seq_exec_no',
            GREATEST(1, COALESCE((
                SELECT MAX(NULLIF(split_part(task_no, '-', 2), '')::bigint)
                FROM exec_task
            ), 0) + 1),
            false
        )
        """
    )
    op.execute(
        """
        SELECT setval(
            'seq_approval_no',
            GREATEST(1, COALESCE((
                SELECT MAX(NULLIF(split_part(request_no, '-', 3), '')::bigint)
                FROM approval_request
            ), 0) + 1),
            false
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS seq_approval_no")
    op.execute("DROP SEQUENCE IF EXISTS seq_exec_no")