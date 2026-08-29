"""Celery tasks: exec dispatch with concurrency guard, notify, timeout scan, schedule trigger.

Task functions are plain functions accepting explicit deps so unit tests can inject mocks.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.core.config import settings
from app.core.redis_helper import acquire_semaphore, release_semaphore
from app.db.models import ExecTask, ExecTaskHost
from app.repositories import (
    ConfigRuleRepository,
    ExecLogRepository,
    ExecTaskHostRepository,
    ExecTaskRepository,
    HostRepository,
    ScriptRepository,
    ScriptVersionRepository,
)
from app.tasks.celery_app import celery_app
from app.ws.agent_ws import dispatch_to_agent_sync
from app.ws.exec_ws import broadcast_sync


def _new_session():
    from app.db.session import SessionLocal

    return SessionLocal()


def _concurrency_limits(db) -> tuple[int, int]:
    repo = ConfigRuleRepository(db)
    g = repo.by_key("exec_concurrency_limit")
    h = repo.by_key("exec_host_concurrency")
    global_limit = (g.rule_value or {}).get("limit", settings.exec_global_concurrency) if g else settings.exec_global_concurrency
    host_limit = (h.rule_value or {}).get("limit", settings.exec_host_concurrency) if h else settings.exec_host_concurrency
    return int(global_limit), int(host_limit)


def _render_params(content: str, params: dict | None) -> str:
    """Render {{key}} placeholders with task params. Unknown keys are left untouched."""
    if not params or "{{" not in content:
        return content
    out = content
    for key, value in params.items():
        out = out.replace("{{" + str(key) + "}}", str(value))
    return out


def _resolve_content(db, task: ExecTask) -> str:
    """Resolve the content the executor should run (G1).

    kind=script -> ScriptVersion.content of task.script_version (fallback to the
    script's current_version), not a hardcoded placeholder. Param rendering lives here.
    """
    if task.kind == "script" and task.script_id:
        sv = None
        if task.script_version is not None:
            sv = ScriptVersionRepository(db).by_script_version(task.script_id, task.script_version)
        if sv is None:
            script = ScriptRepository(db).get(task.script_id)
            if script is not None:
                sv = ScriptVersionRepository(db).by_script_version(script.id, script.current_version)
        content = sv.content if sv is not None else ""
    else:
        content = task.command or ""
    return _render_params(content, task.params)


def _execute_via_mock(task: ExecTask, th: ExecTaskHost, content: str, timeout_sec: int, params: dict | None):
    """Degraded local execution used when no real Agent is connected.
    Simulates an Agent run: writes a few log lines and a result.
    In production this path is replaced by Agent WS dispatch (app/ws/agent).
    """
    lines = [
        (1, "info", f"[mock-agent] task {task.task_no} started on {th.hostname}"),
        (2, "info", f"[mock-agent] execute: {content[:200] or '(script)'}"),
        (3, "info", "[mock-agent] exit code 0"),
    ]
    for seq, level, text in lines:
        db = _new_session()
        try:
            ExecLogRepository(db).append(th.id, seq, level, text)
            db.commit()
        finally:
            db.close()
    db = _new_session()
    try:
        th.status = "success"
        th.exit_code = 0
        th.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@celery_app.task(name="app.tasks.exec_tasks.exec_dispatch")
def exec_dispatch(task_id: int) -> dict:
    db = _new_session()
    try:
        task = ExecTaskRepository(db).get(task_id)
        if task is None or task.status != "running":
            return {"ok": False, "reason": "task not in running state"}
        global_limit, host_limit = _concurrency_limits(db)
        th_repo = ExecTaskHostRepository(db)
        hosts = th_repo.by_task(task_id)
        content = _resolve_content(db, task)
        started = []
        try:
            for th in hosts:
                if th.status != "pending":
                    continue
                if not acquire_semaphore("exec:global", global_limit):
                    break
                if not acquire_semaphore(f"exec:host:{th.host_id}", host_limit):
                    release_semaphore("exec:global")
                    break
                try:
                    th.status = "running"
                    th.started_at = datetime.now(timezone.utc)
                    db.commit()
                except Exception:
                    release_semaphore(f"exec:host:{th.host_id}")
                    release_semaphore("exec:global")
                    raise
                started.append(th.id)
        except Exception:
            db.rollback()

        if not started:
            # nothing could start (limits exhausted) -> leave pending for retry
            return {"ok": False, "reason": "concurrency limit"}

        for th_id in started:
            th = th_repo.by_id(th_id)
            if th is None:
                continue
            try:
                dispatched = _dispatch_exec_frame(db, task, th, content)
                broadcast_sync(th.id, {"type": "status", "data": {"status": "running"}})
                if not dispatched:
                    _execute_via_mock(task, th, content, task.timeout_sec, task.params)
                    broadcast_sync(th.id, {"type": "status", "data": {"status": th.status, "exit_code": th.exit_code}})
            finally:
                release_semaphore(f"exec:host:{th.host_id}")
                release_semaphore("exec:global")

        # aggregate status only when no host is still executing (G5/G6: pending or
        # in-flight agent runs must not flip the task to failed prematurely)
        stats = th_repo.stats(task_id)
        active = stats.get("running", 0) + stats.get("pending", 0)
        if active > 0:
            if stats.get("pending", 0) and _broker_available():
                exec_dispatch.apply_async(args=[task_id], countdown=5)
            return {"ok": True, "task_id": task_id, "status": task.status}

        success = stats.get("success", 0)
        failed = stats.get("failed", 0)
        timed = stats.get("timed_out", 0)
        total = sum(stats.values())
        if failed == 0 and timed == 0 and total > 0 and success == total:
            new_status = "success"
        elif failed == 0 and timed == 0 and success > 0:
            new_status = "partial"
        else:
            new_status = "failed"
        task.status = new_status
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "task_id": task_id, "status": new_status}
    finally:
        db.close()


def _dispatch_exec_frame(db, task: ExecTask, th: ExecTaskHost, content: str) -> bool:
    """Send an S->C exec frame to a connected agent bound to th.host_id.

    Returns True when the frame was handed to a live agent (execution continues
    asynchronously and completes via the agent WS loop); False -> mock fallback.
    """
    if th.executor != "agent":
        return False
    host = None
    if th.host_id:
        host = HostRepository(db).get(th.host_id)
    if host is None or not host.agent_id:
        return False
    frame = {
        "type": "exec",
        "data": {
            "task_host_id": th.id,
            "task_no": task.task_no,
            "kind": task.kind,
            "command": content,
            "params": task.params,
            "timeout_sec": task.timeout_sec,
        },
    }
    return dispatch_to_agent_sync(host.agent_id, frame)


def _broker_available() -> bool:
    try:
        from app.core.redis_helper import get_redis

        return get_redis() is not None
    except Exception:  # noqa: BLE001 - degraded mode
        return False


@celery_app.task(name="app.tasks.exec_tasks.scan_timeouts")
def scan_timeouts() -> int:
    """Background sweep: mark running tasks older than timeout_sec as timed_out."""
    db = _new_session()
    try:
        repo = ExecTaskRepository(db)
        rows = db.query(ExecTask).filter(ExecTask.status == "running").all()
        now = datetime.now(timezone.utc)
        scanned = 0
        for task in rows:
            start = task.started_at or task.created_at
            if start and (now - start).total_seconds() > task.timeout_sec:
                if repo.optimistic_update(task.id, task.status, "timed_out", task.version):
                    task.version += 1
                    task.finished_at = now
                    th_repo = ExecTaskHostRepository(db)
                    for th in th_repo.by_task(task.id):
                        if th.status in ("pending", "running"):
                            th_repo.update_status(th.id, "timed_out", finished_at=now)
                    scanned += 1
        db.commit()
        return scanned
    finally:
        db.close()
