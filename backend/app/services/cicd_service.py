"""CI/CD integration service (P3-5): providers + release orchestration.

Gate order is **feature first** (ticket/workflow pattern): every public function
calls ``_require_feature(db)`` as its first line, THEN ``user.require_perm("…")``
— so with ``feature.cicd`` off ANY caller (admin included) gets 400
``feature disabled``. Routes stay registered (openapi keys never shrink).

Release orchestration **reuses the §13 workflow engine**: triggering a release
creates ONE real ``workflow_run`` (``trigger_type='release'``) whose single
``callback`` node waits for the inbound provider webhook — this module does NOT
re-implement the orchestrator (§14.4).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.security import decrypt_secret, encrypt_secret
from app.db.models.cicd import (
    CICD_PROVIDER_TYPES,
    RELEASE_ENVS,
    RELEASE_TERMINAL_STATUSES,
    CicdProvider,
    Release,
)
from app.db.models.workflow import TERMINAL_RUN_STATUSES, Workflow, WorkflowVersion
from app.repositories import ConfigRuleRepository

# System workflow reused by every release run (single source, §13 reuse).
_RELEASE_WORKFLOW_NAME = "__release_orchestration__"
_RELEASE_DEFINITION = {
    "nodes": [
        {
            "key": "deploy",
            "type": "callback",
            "config": {},
            "depends_on": [],
            "on_success": [],
            "on_failure": [],
        }
    ]
}

# action -> (allowed_from, target_status) — mirrors WORKFLOW_TRANSITIONS (action-keyed).
# pending->deploying->canary->succeeded ; failed->rolled_back ; terminal cancelled.
# `deploy`/`fail` are *reserved* (declared for the full lifecycle) but have NO route:
# `deploying`/`failed` stay API-unreachable until the run-系 seam (release `failed` <-
# workflow_run) lands — a post-P3-5 add-only residual (@架构 ③ amend). Because `failed`
# is unreachable, `rollback` also accepts a reachable `canary` source (amended authority)
# so rollback stays reachable, while `promote` is narrowed to `canary` only.
RELEASE_TRANSITIONS = {
    "deploy": (("pending",), "deploying"),  # reserved (no route)
    "canary": (("pending", "deploying"), "canary"),
    "promote": (("canary",), "succeeded"),
    "fail": (("deploying", "canary"), "failed"),  # reserved (no route)
    "rollback": (("deploying", "canary", "failed"), "rolled_back"),
    "cancel": (("pending", "deploying", "canary"), "cancelled"),
}


# ---------------------------------------------------------------- helpers


def _require_feature(db: Session) -> None:
    """feature.cicd gates behaviour (not routes); default False => 400."""
    rule = ConfigRuleRepository(db).by_key("feature.cicd")
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _encrypt_config(config: dict | None) -> dict | None:
    """Per-value AES-GCM encryption (§14.2 ``config_enc`` 逐值密文)."""
    if not config:
        return None
    out: dict[str, str] = {}
    for key, value in config.items():
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        out[str(key)] = encrypt_secret(raw)
    return out


def _decrypt_config(config_enc: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (config_enc or {}).items():
        try:
            out[str(key)] = decrypt_secret(str(value))
        except Exception:  # noqa: BLE001 - a malformed blob must not 500 the gate
            continue
    return out


def _provider_out(p: CicdProvider) -> dict:
    # Never echo `config_enc` (secret redaction, §14.2).
    return {
        "id": p.id,
        "type": p.type,
        "name": p.name,
        "endpoint": p.endpoint,
        "enabled": p.enabled,
        "status": p.status,
        "last_heartbeat": _iso(p.last_heartbeat),
        "created_by": p.created_by,
        "created_at": _iso(p.created_at),
        "updated_at": _iso(p.updated_at),
    }


def _release_out(r: Release) -> dict:
    return {
        "id": r.id,
        "provider_id": r.provider_id,
        "app": r.app,
        "version": r.version,
        "artifact_ref": r.artifact_ref,
        "env": r.env,
        "status": r.status,
        "workflow_run_id": r.workflow_run_id,
        "target_host_ids": r.target_host_ids,
        "rolled_back_from": r.rolled_back_from,
        "created_by": r.created_by,
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
    }


def _get_provider(db: Session, provider_id: int) -> CicdProvider:
    p = db.get(CicdProvider, provider_id)
    if p is None:
        raise NotFoundError("cicd provider not found")
    return p


def _get_release(db: Session, release_id: int) -> Release:
    r = db.get(Release, release_id)
    if r is None:
        raise NotFoundError("release not found")
    return r


def _apply_release_transition(r: Release, action: str) -> str:
    allowed_from, target = RELEASE_TRANSITIONS[action]
    if r.status not in allowed_from:
        raise ConflictError(f"cannot {action} release in status '{r.status}'")
    r.status = target
    return target


def _audit(db: Session, user, action: str, r: Release) -> None:
    """Explicit audit row for release state changes (§27.3 ⑧)."""
    from app.db.models.notify import AuditLog

    db.execute(
        AuditLog.__table__.insert().values(
            user_id=getattr(user, "id", None),
            username=getattr(user, "username", "") or "",
            module="cicd",
            action=action,
            method="POST",
            path=f"/api/v1/releases/{r.id}",
            params={
                "release_id": r.id,
                "app": r.app,
                "env": r.env,
                "status": r.status,
                "workflow_run_id": r.workflow_run_id,
            },
            ip="",
            user_agent="",
            status=1,
            cost_ms=0,
            trace_id="",
        )
    )


# ---------------------------------------------------------------- providers


def list_providers(db: Session, user, filters: dict, page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("cicd:provider:list")
    stmt = select(CicdProvider)
    if filters.get("name"):
        stmt = stmt.where(CicdProvider.name.like(f"%{filters['name']}%"))
    if filters.get("type"):
        stmt = stmt.where(CicdProvider.type == filters["type"])
    rows = list(db.scalars(stmt.order_by(CicdProvider.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {
        "list": [_provider_out(p) for p in rows[start:start + size]],
        "total": total,
        "page": page,
        "size": size,
    }


def create_provider(db: Session, user, data) -> dict:
    _require_feature(db)
    user.require_perm("cicd:provider:add")
    if data.type not in CICD_PROVIDER_TYPES:
        raise ValidationError(f"type must be one of {sorted(CICD_PROVIDER_TYPES)}")
    p = CicdProvider(
        type=data.type,
        name=data.name,
        endpoint=data.endpoint,
        config_enc=_encrypt_config(data.config),
        enabled=data.enabled,
        status="unknown",
        created_by=getattr(user, "id", None),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _provider_out(p)


def update_provider(db: Session, user, provider_id: int, data) -> dict:
    _require_feature(db)
    user.require_perm("cicd:provider:edit")
    p = _get_provider(db, provider_id)
    if data.name is not None:
        p.name = data.name
    if data.endpoint is not None:
        p.endpoint = data.endpoint
    if data.enabled is not None:
        p.enabled = data.enabled
    if data.config is not None:
        p.config_enc = _encrypt_config(data.config)
    db.commit()
    db.refresh(p)
    return _provider_out(p)


def delete_provider(db: Session, user, provider_id: int) -> None:
    _require_feature(db)
    user.require_perm("cicd:provider:del")
    p = _get_provider(db, provider_id)
    referenced = db.scalar(select(Release.id).where(Release.provider_id == provider_id))
    if referenced is not None:
        raise ConflictError("provider referenced by releases")
    db.delete(p)
    db.commit()


def test_provider(db: Session, user, provider_id: int) -> dict:
    """Connectivity probe (stub/mock per §14 non-goal: no real CI engine)."""
    _require_feature(db)
    user.require_perm("cicd:provider:test")
    p = _get_provider(db, provider_id)
    p.status = "ok"
    p.last_heartbeat = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "type": p.type, "name": p.name, "status": p.status, "ok": True}


# ---------------------------------------------------------------- releases


def list_releases(db: Session, user, filters: dict, page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("release:list")
    stmt = select(Release)
    if filters.get("status"):
        stmt = stmt.where(Release.status == filters["status"])
    if filters.get("app"):
        stmt = stmt.where(Release.app == filters["app"])
    if filters.get("env"):
        stmt = stmt.where(Release.env == filters["env"])
    rows = list(db.scalars(stmt.order_by(Release.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {
        "list": [_release_out(r) for r in rows[start:start + size]],
        "total": total,
        "page": page,
        "size": size,
    }


def create_release(db: Session, user, data) -> dict:
    _require_feature(db)
    user.require_perm("release:add")
    if data.env not in RELEASE_ENVS:
        raise ValidationError(f"env must be one of {sorted(RELEASE_ENVS)}")
    if not (data.version or data.artifact_ref):
        raise ValidationError("release requires `version` or `artifact_ref`")
    _get_provider(db, data.provider_id)
    r = Release(
        provider_id=data.provider_id,
        app=data.app,
        version=data.version,
        artifact_ref=data.artifact_ref,
        env=data.env,
        status="pending",
        target_host_ids=list(data.target_host_ids) if data.target_host_ids else None,
        created_by=getattr(user, "id", None),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _release_out(r)


def get_release(db: Session, user, release_id: int) -> dict:
    _require_feature(db)
    user.require_perm("release:view")
    return _release_out(_get_release(db, release_id))


def _ensure_release_workflow(db: Session, user) -> Workflow:
    wf = db.scalar(select(Workflow).where(Workflow.name == _RELEASE_WORKFLOW_NAME))
    if wf is None:
        wf = Workflow(
            name=_RELEASE_WORKFLOW_NAME,
            description="P3-5 release orchestration (system, §14.4)",
            current_version=1,
            enabled=1,
            created_by=getattr(user, "id", None),
        )
        db.add(wf)
        db.flush()
        db.add(
            WorkflowVersion(
                workflow_id=wf.id,
                version=1,
                definition=_RELEASE_DEFINITION,
                editor_id=getattr(user, "id", None),
            )
        )
        db.commit()
        db.refresh(wf)
    return wf


def _trigger_release_run(db: Session, user, r: Release, action: str):
    """Create the reused §13 ``workflow_run`` (trigger_type='release') for a release."""
    from app.services import workflow_service

    wf = _ensure_release_workflow(db, user)
    run = workflow_service._start_run(
        db,
        user,
        wf,
        _RELEASE_DEFINITION,
        "release",
        {"release_id": r.id, "app": r.app, "env": r.env, "action": action},
        {"release_id": r.id, "action": action},
    )
    r.workflow_run_id = run.id
    return run


def canary_release(db: Session, user, release_id: int) -> dict:
    _require_feature(db)
    user.require_perm("release:canary")
    r = _get_release(db, release_id)
    _apply_release_transition(r, "canary")
    _trigger_release_run(db, user, r, "canary")
    _audit(db, user, "release.canary", r)
    db.commit()
    db.refresh(r)
    return _release_out(r)


def promote_release(db: Session, user, release_id: int) -> dict:
    _require_feature(db)
    user.require_perm("release:promote")
    r = _get_release(db, release_id)
    _apply_release_transition(r, "promote")
    _audit(db, user, "release.promote", r)
    db.commit()
    db.refresh(r)
    return _release_out(r)


def rollback_release(db: Session, user, release_id: int) -> dict:
    _require_feature(db)
    user.require_perm("release:rollback")
    r = _get_release(db, release_id)
    previous = r.workflow_run_id
    _apply_release_transition(r, "rollback")
    r.rolled_back_from = previous
    _audit(db, user, "release.rollback", r)
    db.commit()
    db.refresh(r)
    return _release_out(r)


def cancel_release(db: Session, user, release_id: int) -> dict:
    _require_feature(db)
    user.require_perm("release:cancel")
    r = _get_release(db, release_id)
    _apply_release_transition(r, "cancel")
    if r.workflow_run_id:
        from app.db.models.workflow import WorkflowRun

        run = db.get(WorkflowRun, r.workflow_run_id)
        if run is not None and run.status not in TERMINAL_RUN_STATUSES:
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
    _audit(db, user, "release.cancel", r)
    db.commit()
    db.refresh(r)
    return _release_out(r)


# ---------------------------------------------------------------- inbound webhook


def handle_webhook(db: Session, provider: str, token: str | None, payload) -> dict:
    """Inbound provider callback: **provider-token gated, NOT session** (§14.3).

    Gate order: feature FIRST (flag off -> 400), then provider token (missing or
    mismatched -> 401). No bearer/session is involved.
    """
    _require_feature(db)
    if not token:
        raise UnauthorizedError("provider token required")
    prov = db.scalar(
        select(CicdProvider).where(
            (CicdProvider.type == provider) | (CicdProvider.name == provider)
        )
    )
    if prov is not None:
        expected = _decrypt_config(prov.config_enc).get("token")
        if expected is not None and expected != token:
            raise UnauthorizedError("invalid provider token")
    return {"accepted": True, "provider": provider, "payload": payload}
