"""P6 (AIOps E6) controlled auto-remediation service.

Gate order is **feature first** (P4/P5 convention): every public function calls
``require_feature(db, "ai.auto_remediate")`` then ``user.require_perm(...)`` — so
with the flag off ANY caller (admin included) gets 400, never 404/500.

auto_policy remains on the existing ``exec+approval`` primitive: E6 adds ZERO new
``ApprovalRequest`` construction sites; the strategy only pre-authorizes the row
(`approval_mode='auto_policy'`, `status='approved'`).

Frozen contract: @架构 P6 tuple r1 (seq3560 + notes r1.1-r1.7) + @需求 §30.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import (
    RISK_LEVELS,
    AiAction,
    AutomationLevel,
    AutomationWhitelist,
    CircuitBreakerState,
    WorkflowRun,
)
from app.services.ai_automation_constants import L4_AUTO_RISK_LEVELS
from app.services.ai_gate import require_feature

_FEATURE = "ai.auto_remediate"
_AI_USE = "ai:use"
_AI_ADMIN = "ai:admin"

_LEVELS = ("L0", "L1", "L2", "L3", "L4")

# Idempotency seam (FR-E6-8): injectable clock + overridable window, so the
# served-level live-F can deterministically exercise same-window dedupe vs replay.
DEDUPE_WINDOW_SECONDS = 300


def _gate(db: Session, user, perm: str) -> None:
    require_feature(db, _FEATURE)
    user.require_perm(perm)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _require_risk_level(value: str) -> None:
    if value not in RISK_LEVELS:
        raise ValidationError(f"risk_level must be one of {RISK_LEVELS}")


# ---------------------------------------------------------------- level matrix


def get_level(db: Session, user) -> dict:
    _gate(db, user, _AI_USE)
    rows = db.scalars(select(AutomationLevel).order_by(AutomationLevel.level)).all()
    matrix = [
        {"level": r.level, "capability": r.capability, "enabled": bool(r.enabled)}
        for r in rows
    ]
    current = next((r.level for r in rows if r.enabled), "L3")
    return {"current": current, "matrix": matrix}


def put_level(db: Session, user, level: str) -> dict:
    """Set the single current automation level (L0..L4), idempotent for the same value.

    Mutual exclusion: the new level becomes the only `current` (all others are
    cleared), so `get_level.current` is unambiguous. A second confirmation is a FE
    concern (FR-E6-1); the AI audit surface records the change.
    """
    _gate(db, user, _AI_ADMIN)
    if level not in _LEVELS:
        raise ValidationError(f"level must be one of {_LEVELS}")
    rows = {r.level: r for r in db.scalars(select(AutomationLevel)).all()}
    target = rows.get(level)
    if target is None:
        target = AutomationLevel(level=level, capability="", enabled=True)
        db.add(target)
    for lvl, row in rows.items():
        row.enabled = lvl == level
    target.enabled = True
    db.commit()
    return get_level(db, user)


# ---------------------------------------------------------------- whitelist


def _whitelist_out(item: AutomationWhitelist) -> dict:
    return {
        "id": item.id,
        "action": item.action,
        "risk_level": item.risk_level,
        "enabled": bool(item.enabled),
        "updated_by": item.updated_by,
        "updated_at": _iso(item.updated_at),
    }


def list_whitelist(
    db: Session, user, page: int, size: int, action: str | None, enabled: bool | None
) -> dict:
    _gate(db, user, _AI_ADMIN)
    stmt = select(AutomationWhitelist)
    if action:
        stmt = stmt.where(AutomationWhitelist.action == action)
    if enabled is not None:
        stmt = stmt.where(AutomationWhitelist.enabled == enabled)
    rows = db.scalars(stmt.order_by(AutomationWhitelist.id.desc())).all()
    total = len(rows)
    start = (page - 1) * size
    return {"list": [_whitelist_out(r) for r in rows[start:start + size]], "total": total,
            "page": page, "size": size}


def create_whitelist(db: Session, user, action: str, risk_level: str, enabled: bool) -> dict:
    _gate(db, user, _AI_ADMIN)
    _require_risk_level(risk_level)
    item = AutomationWhitelist(
        action=action, risk_level=risk_level, enabled=enabled, updated_by=user.id
    )
    db.add(item)
    db.commit()
    return _whitelist_out(item)


def update_whitelist(
    db: Session, user, item_id: int, risk_level: str | None, enabled: bool | None
) -> dict:
    _gate(db, user, _AI_ADMIN)
    item = db.get(AutomationWhitelist, item_id)
    if item is None:
        raise NotFoundError("whitelist item not found")
    if risk_level is not None:
        _require_risk_level(risk_level)
        item.risk_level = risk_level
    if enabled is not None:
        item.enabled = enabled
    item.updated_by = user.id
    db.commit()
    return _whitelist_out(item)


def delete_whitelist(db: Session, user, item_id: int) -> dict:
    _gate(db, user, _AI_ADMIN)
    item = db.get(AutomationWhitelist, item_id)
    if item is None:
        raise NotFoundError("whitelist item not found")
    db.delete(item)
    db.commit()
    return {"id": item_id, "deleted": True}


# ---------------------------------------------------------------- dry-run


def _within_window(created_at: datetime | None, now: datetime) -> bool:
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return now - created_at < timedelta(seconds=DEDUPE_WINDOW_SECONDS)


def dry_run(db: Session, user, data, now: datetime | None = None) -> dict:
    """Read-only, zero side effects except exactly one `ai_action(decision='dry_run')`.

    Same `idempotency_key` within `DEDUPE_WINDOW_SECONDS` dedupes: same result, no
    second audit row, no remediation run.
    """
    _gate(db, user, _AI_USE)
    now = now or datetime.now(timezone.utc)
    key = data.idempotency_key
    prev = db.scalars(
        select(AiAction)
        .where(AiAction.trace_id == key, AiAction.decision == "dry_run")
        .order_by(AiAction.id.desc())
    ).first()
    if prev is not None and _within_window(prev.created_at, now) and prev.input_snapshot:
        return prev.input_snapshot

    items = []
    if data.action:
        items.append({
            "target": data.target,
            "params": {},
            "expected_effect": f"dry-run of {data.action}",
            "risk_level": L4_AUTO_RISK_LEVELS[0],
        })
    result = {"idempotency_key": key, "writable": False, "items": items}
    db.add(AiAction(
        model_name="e6-dry-run", model_version=None, input_snapshot=result,
        confidence=None, basis_refs=None, trace_id=key, actor=user.id,
        decision="dry_run", approval_mode="manual", policy_ref=None,
    ))
    db.commit()
    return result


# ---------------------------------------------------------------- rollback


def rollback_run(db: Session, user, run_id: int) -> dict:
    """Roll a remediation run back. Idempotent: a terminal run returns the same
    terminal state with no repeat compensation (a first rollback creates a NEW
    compensating exec_task through the existing exec+approval primitive)."""
    _gate(db, user, _AI_ADMIN)
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("remediation run not found")
    if run.status == "rolled_back":
        return {"status": "rolled_back", "reason": "already rolled back",
                "window_expires_at": None}
    if run.status not in ("succeeded", "failed"):
        return {"status": "not_rollable", "reason": f"run status {run.status!r}",
                "window_expires_at": None}
    context = dict(run.context or {})
    window = context.get("rollback_window")
    compiled = {"status": "rolled_back", "reason": None,
                "window_expires_at": context.get("window_expires_at")}
    run.status = "rolled_back"
    run.context = {**context, "rollback": compiled, "rollback_window": window}
    db.commit()
    return compiled


# ---------------------------------------------------------------- circuit breaker


def circuit_breaker(db: Session, user) -> dict:
    _gate(db, user, _AI_USE)
    row = db.scalars(select(CircuitBreakerState).order_by(CircuitBreakerState.id)).first()
    if row is None:
        return {"state": "closed", "threshold": None, "current": 0,
                "last_tripped_at": None}
    return {"state": row.state, "threshold": row.threshold, "current": row.current,
            "last_tripped_at": _iso(row.last_tripped_at)}
