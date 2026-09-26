"""P3-4b workflow DAG driver (engine host = API process).

Frozen contract: @架构 P3-4b engine tuple **v1.1** (seq2918) + **实施缝裁定**
(seq2920) + **v1.2** (seq2923) + **v1.2.1** (seq2925); @需求 §27.2 full scope.

Design (host ①): ``step(db, run_id)`` is a pure, idempotent single step —
activate ready nodes, advance ``running``/``waiting`` nodes, finalise the run.
``start_driver(run_id)`` runs ``step`` in an **API-process daemon thread** so
``workflow_ws.broadcast_sync`` is same-process and actually delivered (the
cross-process ``exec_ws.broadcast_sync`` no-op gap is architecturally closed;
the Celery worker is never on the WS path). ``DRIVER_AUTOSTART`` is a module
switch (locks set it ``False`` and drive ``step`` directly). ``recover_runs()``
re-starts drivers for ``running`` runs at app startup (single-process
assumption, §27.6): a ``running`` ``exec_task`` node re-polls its existing row
and, if the row is gone, fails with ``engine_restart`` (**no blind re-dispatch**
— at-most-once).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import create_token
from app.db.models.workflow import (
    TERMINAL_RUN_STATUSES,
    WorkflowNodeRun,
    WorkflowRun,
    WorkflowVersion,
)

logger = logging.getLogger(__name__)

# Module-level switch (tuple v1.1 seq2918 / 实施缝 seq2920). Locks monkeypatch it
# to False and call ``step`` directly; the lock asserts the default is True.
DRIVER_AUTOSTART: bool = True

_STEP_LOCK = threading.RLock()
_DRIVERS: dict[int, threading.Thread] = {}
_TICK_SECONDS = 0.05
_CALLBACK_TTL_HOURS = 24
_CALLBACK_DEFAULT_TIMEOUT = 86400
_MAX_TIMEOUT = 86400
_MAX_PAYLOAD_BYTES = 65536
# ApprovalRequest.biz_id is globally UNIQUE (schedule.py) — offset workflow
# approvals into a disjoint large namespace so they never collide with the
#一期 exec/terminal biz_id domain (small integers).
_WORKFLOW_APPROVAL_BIZ_OFFSET = 5_000_000_000

_NODE_TERMINAL = {"succeeded", "failed", "skipped", "cancelled"}
_RUN_TERMINAL = set(TERMINAL_RUN_STATUSES)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ definition


def _load_definition(db, run) -> tuple[dict, dict]:
    row = db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == run.workflow_id,
            WorkflowVersion.version == run.workflow_version,
        )
    )
    definition = (row.definition if row is not None else None) or {}
    defnodes: dict[str, dict] = {}
    for n in definition.get("nodes") or []:
        if isinstance(n, dict) and isinstance(n.get("key"), str):
            defnodes[n["key"]] = n
    return definition, defnodes


def _cfg(defnode: dict | None) -> dict:
    return (defnode or {}).get("config") or {}


def _timeout_sec(defnode: dict | None, definition: dict, node_type: str):
    """Effective node timeout: config ?? definition.defaults ?? type default.

    Range capped at ``[0, 86400]`` (v1.2.1): ``callback`` defaults to its token
    TTL (86400s) so it can never hang forever; ``manual_approval`` defaults to
    ``None`` (long-lived approvals, backed by run cancel). ``0`` is honoured as
    an immediate timeout.
    """
    cfg = _cfg(defnode)
    if "timeout_sec" in cfg:
        t = cfg["timeout_sec"]
    elif "timeout_sec" in (definition.get("defaults") or {}):
        t = definition["defaults"]["timeout_sec"]
    elif node_type == "callback":
        t = _CALLBACK_DEFAULT_TIMEOUT
    else:
        t = None
    if t is None:
        return None
    try:
        t = int(t)
    except (TypeError, ValueError):
        return None
    if t < 0:
        t = 0
    if t > _MAX_TIMEOUT:
        t = _MAX_TIMEOUT
    return t


def _elapsed(node: WorkflowNodeRun) -> float:
    start = node.started_at or node.updated_at or node.created_at
    if start is None:
        return 0.0
    if start.tzinfo is None:  # SQLite returns naive datetimes
        start = start.replace(tzinfo=timezone.utc)
    return (_now() - start).total_seconds()


def _edges(defnodes: dict) -> tuple[dict[str, set], dict[str, set]]:
    on_succ: dict[str, set] = {}
    on_fail: dict[str, set] = {}
    for key, dn in defnodes.items():
        for target in dn.get("on_success") or []:
            on_succ.setdefault(target, set()).add(key)
        for target in dn.get("on_failure") or []:
            on_fail.setdefault(target, set()).add(key)
    return on_succ, on_fail


def _verdict(key, defnodes, on_succ, on_fail, status) -> str:
    """'ready' | 'skip' | 'wait' for a ``pending`` node (tuple C)."""
    dn = defnodes.get(key) or {}
    deps = list(dn.get("depends_on") or [])
    fail_srcs = on_fail.get(key, set())
    succ_srcs = on_succ.get(key, set())
    if any(status.get(s) == "failed" for s in fail_srcs):
        return "ready"  # failure route activates
    if any(status.get(s) == "failed" for s in succ_srcs):
        return "skip"  # success route abandoned
    if any(status.get(d) in {"failed", "skipped", "cancelled"} for d in deps):
        return "skip"  # AND-join unreachable
    if any(status.get(d) != "succeeded" for d in deps):
        return "wait"
    if any(status.get(s) != "succeeded" for s in succ_srcs):
        return "wait"
    return "ready"


# ------------------------------------------------------------------ node state


def _succeed(node: WorkflowNodeRun, extra: dict | None = None) -> None:
    node.status = "succeeded"
    node.finished_at = _now()
    node.error = None
    if extra:
        out = dict(node.output or {})
        out.update(extra)
        node.output = out


def _fail(node: WorkflowNodeRun, reason: str, code: str) -> None:
    node.status = "failed"
    node.error = reason
    out = dict(node.output or {})
    out["reason"] = code
    node.output = out
    node.finished_at = _now()


def _pending_callback_info(run: WorkflowRun, node: WorkflowNodeRun) -> dict:
    token = create_token(
        run.id,
        "wf_callback",
        timedelta(hours=_CALLBACK_TTL_HOURS),
        run_id=run.id,
        node_key=node.node_key,
    )
    return {
        "token": token,
        "url": f"/api/v1/workflow-runs/{run.id}/callback/{node.node_key}",
        "expires_at": (_now() + timedelta(hours=_CALLBACK_TTL_HOURS)).isoformat(),
    }


def _enter_waiting_callback(run: WorkflowRun, node: WorkflowNodeRun) -> None:
    node.started_at = node.started_at or _now()
    out = dict(node.output or {})
    out["callback"] = _pending_callback_info(run, node)
    node.output = out
    node.status = "waiting"


def _create_exec_task(db, run, node, defnode) -> None:
    from app.services import exec_service

    cfg = _cfg(defnode)
    host_ids = list(cfg.get("host_ids") or [])
    kind = cfg.get("kind") or ("script" if cfg.get("script_id") else "command")
    resolved = exec_service.create_exec_task_record(
        db,  # shared core: sensitive gate + approval linkage + executor + dispatch
        name=f"workflow:{node.node_key}"[:128],
        kind=kind,
        target_host_ids=host_ids,
        script_id=cfg.get("script_id"),
        script_version=cfg.get("script_version"),
        command=cfg.get("command"),
        params=cfg.get("params"),
        mode="batch",
        timeout_sec=int(cfg.get("timeout_sec") or 300),
        created_by=run.created_by,
        requester_id=run.created_by,
        visible_group_ids=None,  # system driver == admin scope (US-03 not narrowed)
        remediation=(run.context or {}).get("remediation"),  # P6 E6-3 origination seam
    )
    node.exec_task_id = resolved["id"]
    if resolved.get("approve_required"):
        # Sensitive exec: never silently ``running`` — mirror the一期 approval and
        # block the node until the exec task is approved/terminal.
        node.approval_id = resolved.get("approval_id")
        node.started_at = node.started_at or _now()
        node.status = "waiting"
    else:
        # Mechanism A (@架构 seq3012): commit `node.exec_task_id` BEFORE dispatch so
        # an external `cancel_run` landing in the running window can resolve the
        # linked exec_task instead of orphaning it. Dispatch through the一期 exec
        # primitive (D4, @架构 seq2986): engine host ① forces the in-process branch
        # so the driver never depends on a celery worker consuming the broker.
        db.commit()
        try:
            exec_service._kick_off_exec(db, resolved["id"], in_process=True)
        except Exception:  # noqa: BLE001
            logger.warning("workflow exec_task %s dispatch failed", resolved["id"])


def _poll_exec_task(db, node) -> bool:
    """Follow the linked一期 ``exec_task`` row to its terminal state (R-复用)."""
    from app.db.models.exec import ExecTask

    task = db.get(ExecTask, node.exec_task_id)
    if task is None:
        _fail(node, "engine_restart", "engine_restart")
        return True
    if task.status in ("success", "partial"):
        _succeed(node, {"exec_task_id": node.exec_task_id})
        return True
    if task.status in ("failed", "timed_out", "canceled", "cancelled"):
        _fail(node, "exec_task_failed", "exec_task_failed")
        return True
    if task.status == "running" and node.status == "waiting":
        node.status = "running"  # approval granted -> resume polling
        return True
    return False


def _create_approval(db, run, node) -> None:
    from app.db.models.schedule import ApprovalRequest
    from app.services import approval_service

    approval = ApprovalRequest(
        request_no=approval_service._approval_no(db),  # reuse一期 ID primitive
        biz_type="workflow",
        biz_id=_WORKFLOW_APPROVAL_BIZ_OFFSET + node.id,
        title=f"编排审批：{node.node_key}"[:256],
        reason="",
        requester_id=run.created_by or 0,
        status="pending",
    )
    db.add(approval)
    db.flush()
    node.approval_id = approval.id
    node.started_at = node.started_at or _now()
    node.status = "waiting"


def _advance_running(db, run, node, defnode, definition) -> bool:
    """Advance a node that was already ``running`` before this tick."""
    ntype = node.node_type
    if ntype in ("sleep", "wait"):
        to = _timeout_sec(defnode, definition, ntype)
        if to is not None and _elapsed(node) >= to:
            _fail(node, "timeout", "timeout")
            return True
        cfg = _cfg(defnode)
        due_reached = True
        if ntype == "wait" and cfg.get("until"):
            try:
                due_at = datetime.fromisoformat(str(cfg["until"]).replace("Z", "+00:00"))
                if due_at.tzinfo is None:
                    due_at = due_at.replace(tzinfo=timezone.utc)
                due_reached = _now() >= due_at
            except (TypeError, ValueError):
                due_reached = True
        else:
            due_reached = _elapsed(node) >= float(cfg.get("duration_sec") or 0)
        if due_reached:
            _succeed(node)
            return True
        return False
    if ntype == "callback":
        _enter_waiting_callback(run, node)
        return True
    if ntype == "manual_approval":
        if node.approval_id is None:
            _create_approval(db, run, node)
            return True
        return False
    if ntype == "exec_task":
        if node.exec_task_id is None:
            _create_exec_task(db, run, node, defnode)
            return True
        return _poll_exec_task(db, node)
    return False


def _advance_waiting(db, run, node, defnode, definition) -> bool:
    progressed = False
    if node.node_type == "exec_task" and node.exec_task_id is not None:
        progressed = _poll_exec_task(db, node)
        if node.status != "waiting":
            return progressed
    if node.node_type == "manual_approval" and node.approval_id is not None:
        from app.db.models.schedule import ApprovalRequest

        approval = db.get(ApprovalRequest, node.approval_id)
        if approval is not None:
            if approval.status == "approved":
                _succeed(node)
                return True
            if approval.status in ("rejected", "cancelled", "canceled"):
                _fail(node, "approval_rejected", "approval_rejected")
                return True
    to = _timeout_sec(defnode, definition, node.node_type)
    if to is not None and _elapsed(node) >= to:
        _fail(node, "timeout", "timeout")
        return True
    return progressed


# ------------------------------------------------------------------ step


def step(db, run_id: int) -> bool:
    """One idempotent engine step. Returns True when the run advanced."""
    with _STEP_LOCK:
        run = db.get(WorkflowRun, run_id)
        if run is None or run.status in _RUN_TERMINAL:
            return False
        progressed = False
        if run.status == "pending":
            run.status = "running"
            run.started_at = run.started_at or _now()
            progressed = True

        definition, defnodes = _load_definition(db, run)
        nodes = list(
            db.scalars(select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id)).all()
        )
        on_succ, on_fail = _edges(defnodes)
        status = {n.node_key: n.status for n in nodes}

        activated: set[str] = set()
        for node in nodes:
            if node.status != "pending":
                continue
            verdict = _verdict(node.node_key, defnodes, on_succ, on_fail, status)
            if verdict == "ready":
                node.status = "running"
                node.attempt = (node.attempt or 0) + 1
                node.started_at = _now()
                activated.add(node.node_key)
                status[node.node_key] = "running"
                progressed = True
            elif verdict == "skip":
                node.status = "skipped"
                node.finished_at = _now()
                status[node.node_key] = "skipped"
                progressed = True

        for node in nodes:
            if node.status == "running" and node.node_key not in activated:
                if _advance_running(db, run, node, defnodes.get(node.node_key) or {}, definition):
                    progressed = True

        for node in nodes:
            if node.status == "waiting":
                if _advance_waiting(db, run, node, defnodes.get(node.node_key) or {}, definition):
                    progressed = True

        status = {n.node_key: n.status for n in nodes}
        if run.status != "cancelled" and status and all(s in _NODE_TERMINAL for s in status.values()):
            failed = [n for n in nodes if n.status == "failed"]
            if failed:
                run.status = "failed"
                run.error = failed[0].error or "workflow node failed"
                _on_run_failed(db, run)
            else:
                run.status = "succeeded"
            run.finished_at = _now()
            progressed = True

        db.commit()
        if progressed:
            _broadcast(db, run_id)
        return progressed


def _broadcast(_db, run_id: int) -> None:
    """Best-effort WS push (no-op without a process event loop, e.g. tests)."""
    try:
        from app.ws import workflow_ws

        workflow_ws.broadcast_sync(run_id, {"type": "run", "data": {"run_id": run_id}})
    except Exception:  # noqa: BLE001
        pass


def _on_run_failed(db, run) -> None:
    """P3-6 R1 seam (§架构 tuple v1 B): notify domain seams of a terminal `failed` run.

    Currently only the CI/CD release reacts (a release-linked ``workflow_run``
    failing drives its release to ``failed``). Additive and failure-isolated: a
    seam error must never abort the run finalisation. A non-release run is a no-op
    inside the seam.
    """
    try:
        from app.services import cicd_service

        cicd_service.fail_release_for_run(db, run)
    except Exception:  # noqa: BLE001
        logger.exception("run-failed seam failed (run=%s)", getattr(run, "id", None))


# ------------------------------------------------------------------ driver


def start_driver(run_id: int) -> None:
    """Start (or reuse) the in-process driver thread for a run."""
    if not DRIVER_AUTOSTART:
        return
    existing = _DRIVERS.get(run_id)
    if existing is not None and existing.is_alive():
        return
    thread = threading.Thread(
        target=_driver_loop, args=(run_id,), name=f"wf-driver-{run_id}", daemon=True
    )
    _DRIVERS[run_id] = thread
    thread.start()


def _driver_loop(run_id: int) -> None:
    from app.db.session import SessionLocal

    try:
        while True:
            db = SessionLocal()
            try:
                db.expire_all()
                run = db.get(WorkflowRun, run_id)
                if run is None or run.status in _RUN_TERMINAL:
                    return
                try:
                    step(db, run_id)
                except Exception:  # noqa: BLE001 - never bubble into the request thread
                    logger.exception("workflow driver step failed (run=%s)", run_id)
            finally:
                db.close()
            time.sleep(_TICK_SECONDS)
    except Exception:  # noqa: BLE001
        logger.exception("workflow driver crashed (run=%s)", run_id)


def recover_runs() -> int:
    """Re-start drivers for ``running`` runs (app startup; single-process)."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run_ids = [
            r.id
            for r in db.scalars(select(WorkflowRun).where(WorkflowRun.status == "running")).all()
        ]
    finally:
        db.close()
    for run_id in run_ids:
        start_driver(run_id)
    return len(run_ids)


def scan_timeouts(db) -> int:
    """Beat backstop: advance every non-terminal run one tick (timeout sweep)."""
    run_ids = [
        r.id
        for r in db.scalars(
            select(WorkflowRun).where(WorkflowRun.status.in_(("pending", "running")))
        ).all()
    ]
    count = 0
    for run_id in run_ids:
        try:
            step(db, run_id)
            count += 1
        except Exception:  # noqa: BLE001
            logger.exception("scan_workflow_timeouts step failed (run=%s)", run_id)
    return count
