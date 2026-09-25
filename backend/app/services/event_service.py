"""Unified ops-event write seam (P4 E1).

**Single write seam**: `emit(db, ...)` is the ONLY place an `OpsEvent` row is
constructed (enforced by the static grep lock `test_s5`). Callers participate in
their own transaction (the row is flushed, not committed) so an event can be
written atomically with the change it describes.

Append-only / forward-only: no updates, no backfill.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import OPS_EVENT_SOURCES, OpsEvent


def emit(
    db: Session,
    *,
    entity_type: str,
    entity_id,
    action: str,
    source: str,
    result: str | None = None,
    refs: dict | None = None,
    trace_id: str | None = None,
) -> OpsEvent:
    """Append one normalized ops event and flush it (single write seam)."""
    if source not in OPS_EVENT_SOURCES:
        source = "audit"
    row = OpsEvent(
        ts=datetime.now(timezone.utc),
        entity_type=entity_type,
        entity_id=str(entity_id),
        action=action,
        result=result,
        source=source,
        refs=refs,
        trace_id=trace_id,
    )
    db.add(row)
    db.flush()
    return row
