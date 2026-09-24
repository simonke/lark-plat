"""p2 close-out: dedup active mon_alert per (rule, entity) + partial unique index - add-only

Active-alert uniqueness for a (rule, entity) pair was previously enforced only in
application code (MonAlertRepository.active_by_rule_entity). This migration adds a
database guard:

  1. resolve historical duplicate active rows (keep the newest, id-max, row per
     (rule_id, entity_id) group; the rest move to 'resolved');
  2. create a partial unique index so concurrent writers cannot create a second
     active row for the same (rule_id, entity_id).

The schema change is additive (a new index) and is chained onto the P2-3 head
c3d4e5f6a7b8 to preserve a single alembic head. The data-dedup step is idempotent.
This migration must NOT be applied to the shared live DB (API-level acceptance
only); see the P2 close-out batch ruling (architect seq2140).

Revision ID: e8a1b2c3d4f5
Revises: c3d4e5f6a7b8
Create Date: 2026-09-20 15:40:00.000000
"""
from __future__ import annotations

from alembic import op

revision = "e8a1b2c3d4f5"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None
SHARED_LIVE_DB_FORBIDDEN = True

# Active alert states (MON_ALERT_STATUSES minus 'resolved').
_ACTIVE_STATES = "('pending','firing','acknowledged')"
_INDEX_NAME = "uq_mon_alert_active_rule_entity"

# Keep the max-id active row per (rule_id, entity_id); resolve the rest.
# Idempotent: a second run finds no active row with a higher-id active peer.
# Portable across PostgreSQL (JSONB ->>) and SQLite (JSON text ->>) so the close-out
# lock can exercise it offline without touching the shared DB.
DEDUP_SQL = f"""
UPDATE mon_alert AS a
SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
WHERE a.rule_id IS NOT NULL
  AND a.status IN {_ACTIVE_STATES}
  AND EXISTS (
      SELECT 1 FROM mon_alert AS b
      WHERE b.rule_id = a.rule_id
        AND (b.entity ->> 'entity_id') = (a.entity ->> 'entity_id')
        AND b.status IN {_ACTIVE_STATES}
        AND b.id > a.id
  )
"""

INDEX_SQL = (
    f"CREATE UNIQUE INDEX {_INDEX_NAME} "
    "ON mon_alert (rule_id, (entity ->> 'entity_id')) "
    f"WHERE status IN {_ACTIVE_STATES} AND rule_id IS NOT NULL"
)

DROP_INDEX_SQL = f"DROP INDEX IF EXISTS {_INDEX_NAME}"


def upgrade() -> None:
    op.execute(DEDUP_SQL)
    op.execute(INDEX_SQL)


def downgrade() -> None:
    op.execute(DROP_INDEX_SQL)
