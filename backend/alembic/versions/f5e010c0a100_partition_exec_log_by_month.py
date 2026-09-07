"""monthly RANGE partitioning for exec_log (P2-4)

exec_log is the highest-volume append-only table (per-batch-run log lines).
Monthly RANGE partitions bound table growth and make retention a cheap
`DROP TABLE exec_log_YYYY_MM` instead of a DELETE over an unbounded heap.

PostgreSQL requires the partition key in every unique/PK constraint, so the
schema contract changes are forced:
  - PK (id)                         -> (id, created_at)
  - UNIQUE (task_host_id, seq)      -> (created_at, task_host_id, seq)
No application code reads exec_log by PK id - ExecLogRepository only ever
queries by (task_host_id, seq) via after_seq/max_seq, so this is transparent
to the service layer. Dedup semantics change exactly along with the unique
keys: an exact (created_at, task_host_id, seq) triple is still unique (blocked),
while the same (task_host_id, seq) pair at a *different* timestamp is now
allowed. The app writes seq monotonically per host within a run and never
reuses a seq across a full-run boundary, so this widening does not affect it.

Approach (validated against local PG16.6 scratch DB, this session):
  1. rename exec_log -> exec_log_legacy, drop its PK/unique/indexes so the
     rebuilt constraint names do not collide
  2. create partitioned parent (composite PK + composite unique + FK)
3. pre-create month partitions for existing data months + a 13-month
      forward window (current .. current+12), so the app's now()-backed
      writes always land on a real month partition without runtime DDL
  4. copy legacy rows (explicit created_at, so month routing is deterministic)
  5. drop legacy table + its owned BIGSERIAL sequence; recreate seq owned by
     the new parent's id and seed from max(id) + 1
  6. recreate task_host_id / created_at indexes on the parent (PG 11+ auto
     inherits them to present and future partitions)
  7. DEFAULT partition absorbs any out-of-window month (backfills etc.); the
     13-month window is refreshed by running the alembic chain again

Runtime auto-creation of missing partitions is intentionally NOT used: PG16
rejects CREATE TABLE .. PARTITION OF on the very table an INSERT is targeting
("cannot CREATE TABLE .. because it is being used by active queries"), which
was verified against this session's scratch DB for both row- and
statement-level trigger approaches.

Revision ID: f5e010c0a100
Revises: d1e2f3a4b5c6
Create Date: 2026-09-06 10:00:00.000000
"""
from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa
from alembic import op

revision = "f5e010c0a100"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None

_LEGACY = "exec_log_legacy"
_FORWARD_MONTHS = 12


def _months(conn) -> list[str]:
    """Existing data months plus a forward window, as YYYY_MM (never empty)."""
    rows = conn.execute(
        sa.text("SELECT DISTINCT to_char(created_at, 'YYYY_MM') FROM "
                f"{_LEGACY} ORDER BY 1")
    ).scalars().all()
    base = {r for r in rows}
    first = conn.execute(
        sa.text("SELECT date_trunc('month', now())::date")
    ).scalar()
    for i in range(_FORWARD_MONTHS + 1):
        base.add((first + timedelta(days=31 * i)).strftime("%Y_%m"))
    return sorted(base)


def _month_bounds(part: str) -> tuple[str, str]:
    """Low/next-month bounds for a partition named exec_log_YYYY_MM."""
    y, m = part.rsplit("_", 2)[1], part.rsplit("_", 1)[1]
    d = date(int(y), int(m), 1)
    nd = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return f"{d:%Y-%m-%d}", f"{nd:%Y-%m-%d}"


def _create_partition(part: str) -> None:
    lo, hi = _month_bounds(part)
    op.execute(f"CREATE TABLE {part} PARTITION OF exec_log "
               f"FOR VALUES FROM ('{lo}') TO ('{hi}')")


def upgrade() -> None:
    conn = op.get_bind()

    op.execute(f"ALTER TABLE exec_log RENAME TO {_LEGACY}")
    op.execute(f"ALTER TABLE {_LEGACY} DROP CONSTRAINT IF EXISTS exec_log_pkey")
    op.execute(f"ALTER TABLE {_LEGACY} DROP CONSTRAINT IF EXISTS exec_log_task_host_id_seq_key")
    op.execute("DROP INDEX IF EXISTS ix_exec_log_task_host_id")
    op.execute("DROP INDEX IF EXISTS ix_exec_log_created_at")

    op.execute(
        """
        CREATE TABLE exec_log (
            id BIGINT NOT NULL,
            task_host_id BIGINT NOT NULL,
            seq INTEGER NOT NULL,
            level VARCHAR(16) NOT NULL DEFAULT 'info',
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT exec_log_pkey PRIMARY KEY (id, created_at),
            CONSTRAINT uq_exec_log_created_at_task_host_id_seq
                UNIQUE (created_at, task_host_id, seq),
            CONSTRAINT fk_exec_log_task_host FOREIGN KEY (task_host_id)
                REFERENCES exec_task_host (id) ON DELETE CASCADE
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute("CREATE TABLE exec_log_default PARTITION OF exec_log DEFAULT")

    for month in _months(conn):
        _create_partition("exec_log_" + month)

    op.execute(
        f"INSERT INTO exec_log (id, task_host_id, seq, level, content, created_at) "
        f"SELECT id, task_host_id, seq, level, content, created_at "
        f"FROM {_LEGACY} ORDER BY id"
    )
    # Legacy table dropped last: drops its old indexes and its owned BIGSERIAL
    # sequence, so rebuild the id default explicitly.
    op.execute(f"DROP TABLE {_LEGACY}")

    op.execute("CREATE INDEX ix_exec_log_task_host_id ON exec_log (task_host_id)")
    op.execute("CREATE INDEX ix_exec_log_created_at ON exec_log (created_at)")

    op.execute("CREATE SEQUENCE exec_log_id_seq")
    op.execute(
        "SELECT setval('exec_log_id_seq', "
        "GREATEST(1, COALESCE((SELECT max(id) FROM exec_log), 0) + 1), false)"
    )
    op.execute("ALTER SEQUENCE exec_log_id_seq OWNED BY exec_log.id")
    op.execute(
        "ALTER TABLE exec_log ALTER COLUMN id SET DEFAULT nextval('exec_log_id_seq')"
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS exec_log_id_seq")
    op.execute("DROP TABLE IF EXISTS exec_log CASCADE")
    op.execute(f"ALTER TABLE IF EXISTS {_LEGACY} RENAME TO exec_log")