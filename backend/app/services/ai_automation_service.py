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

import os
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
    RemediationPolicy,
    WorkflowRun,
)
from app.services.ai_automation_constants import L4_AUTO_RISK_LEVELS
from app.services.ai_gate import is_feature_enabled, require_feature

_FEATURE = "ai.auto_remediate"
_AI_USE = "ai:use"
_AI_ADMIN = "ai:admin"

_LEVELS = ("L0", "L1", "L2", "L3", "L4")

# Idempotency seam (FR-E6-8): injectable clock + overridable window, so the
# served-level live-F can deterministically exercise same-window dedupe vs replay.
DEDUPE_WINDOW_SECONDS = 300

# Circuit-breaker threshold single source (FR-E6-4): env override > policy value >
# builtin default. `resolve_threshold` is the ONE place the precedence lives.
_THRESHOLD_ENV = "AI_AUTO_REMEDIATE_CIRCUIT_THRESHOLD"
_DEFAULT_CIRCUIT_THRESHOLD = 3
_GLOBAL_SCOPE = "global"


def _gate(db: Session, user, perm: str) -> None:
    require_feature(db, _FEATURE)
    user.require_perm(perm)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _require_risk_level(value: str) -> None:
    if value not in RISK_LEVELS:
        raise ValidationError(f"risk_level must be one of {RISK_LEVELS}")


def _current_level(db: Session) -> str:
    """Derived `current` = the unique enabled `AutomationLevel` row's level (r1.9
    ①), defaulting to `L3` when none is enabled — never a stored column."""
    rows = db.scalars(select(AutomationLevel)).all()
    return next((r.level for r in rows if r.enabled), "L3")


# ------------------------------------------------- E6 auto-policy resolution

def resolve_auto_policy(db: Session, remediation: dict | None) -> dict | None:
    """FR-E6-3 hit test (r1.9 four-way conjunction). Returns `{"policy_ref":…}` on a
    hit, else `None` (=> the caller leaves the approval row `manual`/`pending`).

    Silent by design: flag off or any miss returns `None` — never raises — so the
    shared exec core stays byte-identical to P5 when E6 is disabled.
    """
    if not remediation or not is_feature_enabled(db, _FEATURE):
        return None
    if remediation.get("risk_level") not in L4_AUTO_RISK_LEVELS:
        return None
    if _current_level(db) != "L4":
        return None
    if _breaker_state(db) == "open":  # r1.10 halt: an open breaker forces manual
        return None
    action = remediation.get("action")
    # A2 (r1.9): ambiguous (>1) OR empty policy set => fail-closed manual.
    policies = db.scalars(
        select(RemediationPolicy).where(
            RemediationPolicy.asset_class == remediation.get("asset_class"),
            RemediationPolicy.op_type == remediation.get("op_type"),
            RemediationPolicy.level == "L4",
            RemediationPolicy.whitelist_ref.is_not(None),
            RemediationPolicy.verification_ref.is_not(None),
        )
    ).all()
    if len(policies) != 1:
        return None
    policy = policies[0]
    if action != policy.whitelist_ref:  # ④ policy -> whitelist explicit reference
        return None
    whitelisted = db.scalars(
        select(AutomationWhitelist).where(
            AutomationWhitelist.action == policy.whitelist_ref,  # ⑤ config risk
            AutomationWhitelist.enabled.is_(True),
            AutomationWhitelist.risk_level.in_(L4_AUTO_RISK_LEVELS),
        )
    ).first()
    if whitelisted is None:
        return None
    return {"policy_ref": f"remediation_policy:{policy.id}"}


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
    if level == "L4":
        # FR-E6-4 fail-closed (r1.9 B): L4 activation needs a governed policy set
        # whose every `level=='L4'` row carries a verification_ref. Empty set is
        # NOT "vacuously ok" — enabling L4 with no policy is refused (422).
        l4_policies = db.scalars(
            select(RemediationPolicy).where(RemediationPolicy.level == "L4")
        ).all()
        if not l4_policies or any(p.verification_ref is None for p in l4_policies):
            raise ValidationError("L4 requires governed policies with verification_ref")
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
    remediation = context.get("remediation")
    rollback_ref = None
    if remediation and is_feature_enabled(db, _FEATURE):
        # FR-E6-4 (r1.1/r1.6): the FIRST rollback creates a NEW compensating
        # exec_task through the existing exec+approval primitive (never a new
        # construction site); the reversal command comes from the original run's
        # `context["remediation"]`. Repeat rollback returns early above => Δ0.
        from app.services import exec_service  # lazy import: avoid a service cycle

        comp = exec_service.create_exec_task_record(
            db,
            name=str(remediation.get("name") or f"rollback:{run_id}")[:128],
            kind=remediation.get("kind") or ("script" if remediation.get("script_id") else "command"),
            target_host_ids=list(remediation.get("target_host_ids") or []),
            script_id=remediation.get("script_id"),
            script_version=remediation.get("script_version"),
            command=remediation.get("command"),
            params=remediation.get("params"),
            created_by=run.created_by,
            requester_id=run.created_by,
            visible_group_ids=None,
        )
        rollback_ref = f"exec_task:{comp['id']}"
        db.add(AiAction(
            model_name="e6-rollback", model_version=None, input_snapshot=None,
            confidence=None, basis_refs=None, trace_id=f"rollback:{run_id}",
            actor=run.created_by, decision="adopted", approval_mode="manual",
            policy_ref=None, rollback_ref=rollback_ref,
        ))
        db.flush()
    compiled = {"status": "rolled_back", "reason": None,
                "window_expires_at": context.get("window_expires_at")}
    run.status = "rolled_back"
    run.context = {**context, "rollback": compiled, "rollback_window": window,
                   **({"rollback_ref": rollback_ref} if rollback_ref else {})}
    db.commit()
    return compiled


# ---------------------------------------------------------------- circuit breaker

def _breaker_state(db: Session) -> str:
    row = db.scalars(
        select(CircuitBreakerState).where(CircuitBreakerState.scope == _GLOBAL_SCOPE)
    ).first()
    return row.state if row is not None else "closed"


def resolve_threshold(db: Session, *, policy=None) -> int:
    """FR-E6-4 circuit-breaker threshold single source (r1.9 ③ / r1.10 @架构 `3635`).
    Precedence: env override > `policy.circuit_threshold` (non-null) > the global
    `CircuitBreakerState('global').threshold` row > builtin default. Kept in ONE place
    so trip / halt / GET cannot drift."""
    raw = os.getenv(_THRESHOLD_ENV)
    if raw not in (None, ""):
        try:
            return int(raw)
        except ValueError:
            pass
    if policy is not None and getattr(policy, "circuit_threshold", None) is not None:
        return int(policy.circuit_threshold)
    row = db.scalars(
        select(CircuitBreakerState).where(CircuitBreakerState.scope == _GLOBAL_SCOPE)
    ).first()
    if row is not None and row.threshold is not None:
        return int(row.threshold)
    return _DEFAULT_CIRCUIT_THRESHOLD


def record_verification_result(db: Session, *, policy=None, ok: bool) -> dict:
    """FR-E6-4 / r1.10 breaker FSM: closed -> open -> half -> closed.

    A failure at/over `resolve_threshold(db, policy=…)` trips the breaker `open`; a
    success while `open` half-opens it; a success while `half` closes it (and resets
    the failure counter). No clock dependency (the caller drives it deterministically)."""
    threshold = resolve_threshold(db, policy=policy)
    row = db.scalars(
        select(CircuitBreakerState).where(CircuitBreakerState.scope == _GLOBAL_SCOPE)
    ).first()
    if row is None:
        row = CircuitBreakerState(scope=_GLOBAL_SCOPE, state="closed", current=0, threshold=None)
        db.add(row)
        db.flush()
    if row.state == "half":
        if ok:
            row.state, row.current, row.last_tripped_at = "closed", 0, None
        else:
            row.state = "open"
            row.last_tripped_at = datetime.now(timezone.utc)
    elif row.state == "open":
        if ok:  # open -> half
            row.state = "half"
    else:  # closed
        if ok:
            row.current = 0
        else:
            row.current = (row.current or 0) + 1
            if row.current >= threshold:
                row.state = "open"
                row.threshold = threshold
                row.last_tripped_at = datetime.now(timezone.utc)
    db.commit()
    return {"state": row.state, "current": row.current, "threshold": row.threshold}


def circuit_breaker(db: Session, user) -> dict:
    _gate(db, user, _AI_USE)
    threshold = resolve_threshold(db, policy=None)
    row = db.scalars(
        select(CircuitBreakerState).where(CircuitBreakerState.scope == _GLOBAL_SCOPE)
    ).first()
    if row is None:
        return {"state": "closed", "threshold": threshold, "current": 0,
                "last_tripped_at": None}
    return {"state": row.state, "threshold": threshold, "current": row.current,
            "last_tripped_at": _iso(row.last_tripped_at)}
