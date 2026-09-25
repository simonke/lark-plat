"""Workflow service (P3-4): Playbook definition/versioning + DAG run state.

Gate order is **feature first** (ticket pattern): every public function calls
``_require_feature(db)`` as its first line, THEN ``user.require_perm("workflow:…")``
— so with the flag off ANY caller (admin included) gets 400 ``feature disabled``.
Routes stay registered (openapi keys never shrink).

Definition validation (§13.2): ``nodes[{key,type∈NODE_TYPES,config,depends_on[],
on_success[],on_failure[]}]`` — duplicate keys, unknown refs, cycles and the
baseline caps (nodes<=100 / edges<=500) all raise **422**.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.security import create_token
from app.db.models.workflow import (
    NODE_TYPES,
    TRIGGER_TYPES,
    Workflow,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowVersion,
)
from app.repositories import ConfigRuleRepository
from app.schemas import workflow as sch

_MAX_NODES = 100
_MAX_EDGES = 500
_MAX_CALLBACK_PAYLOAD = 65536

# action -> (allowed_from, target_status) — mirrors TICKET_TRANSITIONS (action-keyed).
# run: pending -> running -> (succeeded|failed|cancelled); cancel only pre-terminal.
WORKFLOW_TRANSITIONS = {
    "start": (("pending",), "running"),
    "succeed": (("running",), "succeeded"),
    "fail": (("running",), "failed"),
    "cancel": (("pending", "running"), "cancelled"),
}


# ---------------------------------------------------------------- helpers


def _require_feature(db: Session) -> None:
    """feature.workflow gates behaviour (not routes); default False => 400."""
    rule = ConfigRuleRepository(db).by_key("feature.workflow")
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _get_workflow(db: Session, workflow_id: int) -> Workflow:
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise NotFoundError("workflow not found")
    return wf


def _version_row(db: Session, workflow_id: int, version: int) -> WorkflowVersion | None:
    return db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow_id,
            WorkflowVersion.version == version,
        )
    )


def _next_version(db: Session, workflow_id: int) -> int:
    cur = db.scalar(
        select(func.max(WorkflowVersion.version)).where(
            WorkflowVersion.workflow_id == workflow_id
        )
    )
    return int(cur or 0) + 1


def _workflow_out(wf: Workflow, definition: dict | None) -> dict:
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "current_version": wf.current_version,
        "enabled": wf.enabled,
        "definition": definition,
        "created_by": wf.created_by,
        "created_at": _iso(wf.created_at),
        "updated_at": _iso(wf.updated_at),
    }


def _version_out(v: WorkflowVersion) -> dict:
    return {
        "id": v.id,
        "workflow_id": v.workflow_id,
        "version": v.version,
        "definition": v.definition,
        "editor_id": v.editor_id,
        "created_at": _iso(v.created_at),
    }


def _run_out(r: WorkflowRun) -> dict:
    return {
        "id": r.id,
        "workflow_id": r.workflow_id,
        "workflow_version": r.workflow_version,
        "status": r.status,
        "trigger_type": r.trigger_type,
        "trigger_ref": r.trigger_ref,
        "context": r.context,
        "started_at": _iso(r.started_at),
        "finished_at": _iso(r.finished_at),
        "error": r.error,
        "created_by": r.created_by,
        "created_at": _iso(r.created_at),
    }


def _node_out(n: WorkflowNodeRun) -> dict:
    return {
        "id": n.id,
        "run_id": n.run_id,
        "node_key": n.node_key,
        "node_type": n.node_type,
        "status": n.status,
        "exec_task_id": n.exec_task_id,
        "approval_id": n.approval_id,
        "attempt": n.attempt,
        "output": n.output,
        "error": n.error,
        "started_at": _iso(n.started_at),
        "finished_at": _iso(n.finished_at),
    }


def _assert_acyclic(keys: set[str], edges: list[tuple[str, str]]) -> None:
    adj: dict[str, list[str]] = defaultdict(list)
    for src, dst in edges:
        adj[src].append(dst)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in keys}

    def visit(node: str) -> None:
        color[node] = GRAY
        for nxt in adj[node]:
            if color[nxt] == GRAY:
                raise ValidationError("workflow definition contains a cycle")
            if color[nxt] == WHITE:
                visit(nxt)
        color[node] = BLACK

    for k in keys:
        if color[k] == WHITE:
            visit(k)


def _validate_definition(definition: dict | None) -> dict:
    if not isinstance(definition, dict):
        raise ValidationError("definition must be an object")
    nodes = definition.get("nodes")
    if not isinstance(nodes, list):
        raise ValidationError("definition.nodes must be a list")
    if len(nodes) > _MAX_NODES:
        raise ValidationError(f"definition exceeds node cap {_MAX_NODES}")

    keys: set[str] = set()
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValidationError(f"node[{i}] must be an object")
        key = node.get("key")
        if not isinstance(key, str) or not key:
            raise ValidationError(f"node[{i}].key is required")
        if key in keys:
            raise ValidationError(f"duplicate node key: {key}")
        keys.add(key)
        if node.get("type") not in NODE_TYPES:
            raise ValidationError(
                f"node '{key}' type must be one of {sorted(NODE_TYPES)}"
            )

    edges: list[tuple[str, str]] = []
    edge_count = 0
    for node in nodes:
        key = node["key"]
        for field in ("depends_on", "on_success", "on_failure"):
            refs = node.get(field) or []
            if not isinstance(refs, list):
                raise ValidationError(f"node '{key}'.{field} must be a list")
            for ref in refs:
                if ref not in keys:
                    raise ValidationError(
                        f"node '{key}'.{field} references unknown node '{ref}'"
                    )
                edges.append((ref, key))
                edge_count += 1
    if edge_count > _MAX_EDGES:
        raise ValidationError(f"definition exceeds edge cap {_MAX_EDGES}")
    _assert_acyclic(keys, edges)
    return definition


def _apply_run_transition(run: WorkflowRun, action: str) -> str:
    allowed_from, target = WORKFLOW_TRANSITIONS[action]
    if run.status not in allowed_from:
        raise ConflictError(f"cannot {action} run in status '{run.status}'")
    run.status = target
    return target


def _start_run(
    db: Session, user, wf: Workflow, definition: dict, trigger_type: str,
    trigger_ref: dict | None, context: dict | None,
) -> WorkflowRun:
    run = WorkflowRun(
        workflow_id=wf.id,
        workflow_version=wf.current_version,
        status="pending",
        trigger_type=trigger_type,
        trigger_ref=trigger_ref,
        context=context,
        created_by=getattr(user, "id", None),
    )
    db.add(run)
    db.flush()
    for node in definition.get("nodes") or []:
        db.add(
            WorkflowNodeRun(
                run_id=run.id,
                node_key=node["key"],
                node_type=node["type"],
                status="pending",
                attempt=0,
            )
        )
    db.commit()
    db.refresh(run)
    from app.services import workflow_engine

    if workflow_engine.DRIVER_AUTOSTART:
        workflow_engine.start_driver(run.id)
    return run


# ---------------------------------------------------------------- CRUD / versions


def list_workflows(db: Session, user, filters: dict[str, Any], page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:list")
    stmt = select(Workflow)
    if filters.get("name"):
        stmt = stmt.where(Workflow.name.like(f"%{filters['name']}%"))
    if filters.get("enabled") is not None:
        stmt = stmt.where(Workflow.enabled == filters["enabled"])
    rows = list(db.scalars(stmt.order_by(Workflow.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {
        "list": [_workflow_out(w, None) for w in rows[start:start + size]],
        "total": total,
        "page": page,
        "size": size,
    }


def create_workflow(db: Session, user, data: sch.WorkflowCreate) -> dict:
    _require_feature(db)
    user.require_perm("workflow:add")
    if db.scalar(select(Workflow).where(Workflow.name == data.name)) is not None:
        raise ConflictError("workflow name already exists")
    definition = data.definition if data.definition is not None else {"nodes": []}
    _validate_definition(definition)
    wf = Workflow(
        name=data.name,
        description=data.description or "",
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
            definition=definition,
            editor_id=getattr(user, "id", None),
        )
    )
    db.commit()
    db.refresh(wf)
    return _workflow_out(wf, definition)


def get_workflow(db: Session, user, workflow_id: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:view")
    wf = _get_workflow(db, workflow_id)
    version_row = _version_row(db, wf.id, wf.current_version)
    definition = version_row.definition if version_row else None
    return _workflow_out(wf, definition)


def update_workflow(db: Session, user, workflow_id: int, data: sch.WorkflowUpdate) -> dict:
    _require_feature(db)
    user.require_perm("workflow:edit")
    wf = _get_workflow(db, workflow_id)
    if data.name is not None and data.name != wf.name:
        dup = db.scalar(select(Workflow).where(Workflow.name == data.name))
        if dup is not None:
            raise ConflictError("workflow name already exists")
        wf.name = data.name
    if data.description is not None:
        wf.description = data.description
    if data.enabled is not None:
        wf.enabled = data.enabled
    db.commit()
    db.refresh(wf)
    version_row = _version_row(db, wf.id, wf.current_version)
    return _workflow_out(wf, version_row.definition if version_row else None)


def delete_workflow(db: Session, user, workflow_id: int) -> None:
    _require_feature(db)
    user.require_perm("workflow:del")
    wf = _get_workflow(db, workflow_id)
    referenced = db.scalar(
        select(func.count()).select_from(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id)
    )
    if referenced:
        raise ConflictError("workflow referenced by runs")
    for v in db.scalars(
        select(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
    ).all():
        db.delete(v)
    db.delete(wf)
    db.commit()


def create_version(db: Session, user, workflow_id: int, data: sch.WorkflowVersionCreate) -> dict:
    _require_feature(db)
    user.require_perm("workflow:version")
    wf = _get_workflow(db, workflow_id)
    definition = _validate_definition(data.definition)
    version = _next_version(db, wf.id)
    row = WorkflowVersion(
        workflow_id=wf.id,
        version=version,
        definition=definition,
        editor_id=getattr(user, "id", None),
    )
    db.add(row)
    wf.current_version = version
    db.commit()
    db.refresh(row)
    return _version_out(row)


def list_versions(db: Session, user, workflow_id: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:view")
    wf = _get_workflow(db, workflow_id)
    rows = list(
        db.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == wf.id)
            .order_by(WorkflowVersion.version.desc())
        ).all()
    )
    return {"list": [_version_out(v) for v in rows], "total": len(rows)}


def rollback_workflow(db: Session, user, workflow_id: int, version: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:rollback")
    wf = _get_workflow(db, workflow_id)
    row = _version_row(db, wf.id, version)
    if row is None:
        raise NotFoundError("workflow version not found")
    wf.current_version = version
    db.commit()
    db.refresh(wf)
    return _workflow_out(wf, row.definition)


# ---------------------------------------------------------------- runs


def run_workflow(
    db: Session, user, workflow_id: int, idempotency_key: str | None,
    data: sch.WorkflowRunIn | None,
) -> dict:
    _require_feature(db)
    user.require_perm("workflow:run")
    wf = _get_workflow(db, workflow_id)
    version_row = _version_row(db, wf.id, wf.current_version)
    if version_row is None:
        raise BadRequestError("workflow has no definition to run")
    definition = version_row.definition or {"nodes": []}

    trigger_type = (data.trigger_type if data else None) or "manual"
    if trigger_type not in TRIGGER_TYPES:
        raise ValidationError(f"trigger_type must be one of {sorted(TRIGGER_TYPES)}")

    trigger_ref = dict(data.trigger_ref) if (data and data.trigger_ref) else {}
    if idempotency_key:
        for existing in db.scalars(
            select(WorkflowRun).where(WorkflowRun.workflow_id == wf.id)
        ).all():
            if (existing.trigger_ref or {}).get("idempotency_key") == idempotency_key:
                return {"run_id": existing.id}
        trigger_ref["idempotency_key"] = idempotency_key

    context = data.context if data else None
    run = _start_run(db, user, wf, definition, trigger_type, trigger_ref or None, context)
    return {"run_id": run.id}


def list_runs(db: Session, user, filters: dict[str, Any], page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:view")
    stmt = select(WorkflowRun)
    if filters.get("workflow_id") is not None:
        stmt = stmt.where(WorkflowRun.workflow_id == filters["workflow_id"])
    if filters.get("status"):
        stmt = stmt.where(WorkflowRun.status == filters["status"])
    rows = list(db.scalars(stmt.order_by(WorkflowRun.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {
        "list": [_run_out(r) for r in rows[start:start + size]],
        "total": total,
        "page": page,
        "size": size,
    }


def get_run(db: Session, user, run_id: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:view")
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("workflow run not found")
    nodes = list(
        db.scalars(
            select(WorkflowNodeRun)
            .where(WorkflowNodeRun.run_id == run_id)
            .order_by(WorkflowNodeRun.id)
        ).all()
    )
    return {"run": _run_out(run), "nodes": [_node_out(n) for n in nodes]}


def cancel_run(db: Session, user, run_id: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:cancel")
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("workflow run not found")
    _apply_run_transition(run, "cancel")
    run.finished_at = datetime.now(timezone.utc)
    now = datetime.now(timezone.utc)
    from app.db.models.exec import ExecTask

    for node in db.scalars(
        select(WorkflowNodeRun).where(
            WorkflowNodeRun.run_id == run_id,
            WorkflowNodeRun.status.in_(("pending", "running", "waiting")),
        )
    ).all():
        if node.node_type == "exec_task" and node.exec_task_id:
            task = db.get(ExecTask, node.exec_task_id)
            if task is not None and task.status in ("created", "running", "awaiting_approval"):
                task.status = "cancelled"
        node.status = "skipped"
        node.finished_at = now
    db.commit()
    db.refresh(run)
    return _run_out(run)


def retry_run(db: Session, user, run_id: int) -> dict:
    _require_feature(db)
    user.require_perm("workflow:run")
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("workflow run not found")
    wf = _get_workflow(db, run.workflow_id)
    version_row = _version_row(db, wf.id, run.workflow_version)
    definition = version_row.definition if version_row else {"nodes": []}
    new_run = _start_run(
        db, user, wf, definition, run.trigger_type,
        {"retry_of": run.id}, run.context,
    )
    return {"run_id": new_run.id}


def run_ws_token(db: Session, user, run_id: int) -> dict:
    """Short-lived (5min) WS token bound to the run (mirror exec/transfer)."""
    _require_feature(db)
    user.require_perm("workflow:view")
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("workflow run not found")
    return {"token": create_token(run_id, "ws", timedelta(minutes=5))}


def callback_node(
    db: Session, run_id: int, node_key: str, token: str | None, payload: Any
) -> dict:
    """Node-level callback activation (tuple K/seq2923).

    Gate order: feature FIRST (flag off -> 400 for any caller), then run (404),
    then node token (401), then node state (409). The token is single-use in
    effect: once the node leaves ``waiting`` a second callback is 409.
    """
    _require_feature(db)
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise NotFoundError("workflow run not found")
    if not token:
        raise UnauthorizedError("callback token required")
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        raise UnauthorizedError("invalid callback token")
    if claims.get("type") != "wf_callback":
        raise UnauthorizedError("invalid callback token")
    try:
        bound = int(claims.get("run_id")) == run_id and claims.get("node_key") == node_key
    except (TypeError, ValueError):
        bound = False
    if not bound:
        raise UnauthorizedError("invalid callback token")

    node = db.scalar(
        select(WorkflowNodeRun).where(
            WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == node_key
        )
    )
    if node is None:
        raise NotFoundError("workflow node not found")
    if node.node_type != "callback" or node.status != "waiting":
        raise ConflictError("node is not awaiting callback")

    raw = json.dumps(payload if payload is not None else None).encode("utf-8")
    if len(raw) > _MAX_CALLBACK_PAYLOAD:
        raise ValidationError("callback_payload_too_large")

    out = dict(node.output or {})
    out["payload"] = payload
    node.output = out
    node.status = "succeeded"
    node.finished_at = datetime.now(timezone.utc)
    node.error = None
    db.commit()
    db.refresh(node)

    from app.services import workflow_engine

    if workflow_engine.DRIVER_AUTOSTART:
        workflow_engine.start_driver(run_id)
    return {"run_id": run_id, "node_key": node_key, "status": "succeeded"}
