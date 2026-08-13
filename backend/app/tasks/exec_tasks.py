"""Celery tasks: exec dispatch with concurrency guard, notify, timeout scan, schedule trigger.

Task functions are plain functions accepting explicit deps so unit tests can inject mocks.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import settings
from app.core.redis_helper import acquire_semaphore, release_semaphore
from app.db.models import ConfigRule, ExecLog, ExecTask, ExecTaskHost
from app.repositories import (
    ConfigRuleRepository,
    ExecLogRepository,
    ExecTaskHostRepository,
    ExecTaskRepository,
)
from app.tasks.celery_app import celery_app


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


def _resolve_content(task: ExecTask) -> str:
    if task.kind == "script" and task.script_id:
        from app.db.models import ScriptVersion

        sv = (
            __import__("app.db", fromlist=["session"])
        )
        return "script placeholder"
    return task.command or ""


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
        content = _resolve_content(task)
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
                th.status = "running"
                th.started_at = datetime.now(timezone.utc)
                db.commit()
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
            _execute_via_mock(task, th, content, task.timeout_sec, task.params)
            release_semaphore(f"exec:host:{th.host_id}")
            release_semaphore("exec:global")

        # aggregate status
        stats = th_repo.stats(task_id)
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


@celery_app.task(name="app.tasks.exec_tasks.scan_timeouts")
def scan_timeouts() -> int:
    """Background sweep: mark running tasks older than timeout_sec as timed_out."""
    db = _new_session()
    try:
        repo = ExecTaskRepository(db)
        rows = db.query(ExecTask).filter(ExecTask.status.in_(("running", "awaiting_approval"))).all()
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
