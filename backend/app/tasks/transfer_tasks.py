"""Celery tasks: transfer dispatch with per-host channel resolution, degraded
marking, task aggregation (mirrors exec_dispatch structure).

Task functions are plain functions accepting explicit deps so unit tests can
inject mocks (same convention as exec_tasks).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.models import Host, TransferHost, TransferTask
from app.repositories import (
    FileItemRepository,
    HostRepository,
    TransferHostRepository,
    TransferLogRepository,
    TransferTaskRepository,
)
from app.services.transfer_channels import resolve_agent_channel
from app.tasks.celery_app import celery_app
from app.ws.transfer_ws import broadcast_sync

logger = logging.getLogger(__name__)


def _new_session():
    from app.db.session import SessionLocal

    return SessionLocal()


def _append_log(db, th: TransferHost, content: str, level: str = "info") -> None:
    repo = TransferLogRepository(db)
    repo.append(th.id, repo.max_seq(th.id) + 1, level, content)


def _mark_degraded(db, th: TransferHost, reason: str) -> None:
    th_repo = TransferHostRepository(db)
    th_repo.update_status(th.id, "degraded", error=reason, finished_at=datetime.now(timezone.utc))
    _append_log(db, th, f"channel unavailable: {reason}", level="error")
    broadcast_sync(th.id, {"type": "status", "data": {"status": "degraded", "error": reason}})
    db.commit()


def _mark_failed(db, th: TransferHost, error: str) -> None:
    th_repo = TransferHostRepository(db)
    th_repo.update_status(th.id, "failed", error=error, finished_at=datetime.now(timezone.utc))
    _append_log(db, th, f"failed: {error}", level="error")
    broadcast_sync(th.id, {"type": "status", "data": {"status": "failed", "error": error}})
    db.commit()


def _dispatch_host(db, task: TransferTask, th: TransferHost) -> None:
    """Resolve the host channel and start the transfer (or degrade cleanly)."""
    host = HostRepository(db).get(th.host_id) if th.host_id else None
    channel = resolve_agent_channel(db, host)
    if channel is None:
        _mark_degraded(db, th, "no agent channel available (ssh fallback not enabled in this batch)")
        return

    th_repo = TransferHostRepository(db)
    th_repo.update_status(th.id, "transferring", started_at=datetime.now(timezone.utc))
    db.commit()
    _append_log(db, th, f"channel={channel.channel_kind} mode={task.mode} target={task.target_path}")

    if task.mode == "push":
        if task.package_id is None:
            _mark_failed(db, th, "push task without package")
            return
        items = FileItemRepository(db).by_package(task.package_id)
        if not items:
            _mark_failed(db, th, "package has no files")
            return
        for item in items:
            _append_log(db, th, f"transfer file {item.rel_path} size={item.size} verify={bool(task.verify)}")
            ok = channel.push(
                db, task, th, item, offset=th.current_offset or 0,
                target_path=task.target_path, overwrite=task.overwrite,
                verify=task.verify, limit_mbps=task.limit_mbps,
            )
            if not ok:
                _mark_degraded(db, th, "agent unreachable during dispatch")
                return
    else:
        from app.services.transfer_service import _pull_whitelist, path_within_whitelist

        if not task.source_host_path or not path_within_whitelist(task.source_host_path, _pull_whitelist(db)):
            _mark_failed(db, th, "source_host_path outside pull whitelist")
            return
        _append_log(db, th, f"fetch {task.source_host_path} verify={bool(task.verify)}")
        ok = channel.fetch(db, task, th, task.source_host_path, task.target_path,
                           offset=th.current_offset or 0, verify=task.verify)
        if not ok:
            _mark_degraded(db, th, "agent unreachable during fetch dispatch")


def _maybe_finalize(db, task: TransferTask) -> None:
    """Aggregate task status when every host reached a terminal state.

    degraded hosts are not counted as hard failure (requirements ruling): a task
    is success when every non-degraded host succeeded.
    """
    if task.status != "processing":
        return
    th_repo = TransferHostRepository(db)
    stats = th_repo.stats(task.id)
    if not stats:
        return
    if th_repo.active_count(task.id) > 0:
        return
    success = stats.get("success", 0)
    degraded = stats.get("degraded", 0)
    failed = stats.get("failed", 0) + stats.get("verify_failed", 0) + stats.get("canceled", 0)
    total = sum(stats.values())
    new_status: str | None = None
    if total > 0 and success == total:
        new_status = "success"
    elif success > 0:
        new_status = "partial"
    elif failed == 0 and degraded > 0:
        new_status = "partial"
    else:
        new_status = "failed"
    if not TransferTaskRepository(db).optimistic_update(task.id, "processing", new_status, task.version):
        return
    task.status = new_status
    task.version += 1
    task.finished_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("transfer: task %s aggregated to %s (stats=%s)", task.id, new_status, stats)


@celery_app.task(name="app.tasks.transfer_tasks.transfer_dispatch")
def transfer_dispatch(task_id: int) -> dict:
    """One pass over non-terminal transfer_host rows: dispatch or degrade. When
    live agents stay connected, the agent WS loop continues the flow (file_chunk_ack /
    file_result) and finalizes per-host/task states."""
    db = _new_session()
    try:
        task = TransferTaskRepository(db).get(task_id)
        if task is None:
            return {"ok": False, "reason": "task not found"}
        if task.status == "canceled":
            return {"ok": False, "reason": "task canceled"}
        if task.status == "processing":
            for th in TransferHostRepository(db).by_task(task_id):
                if th.status != "pending":
                    continue
                _dispatch_host(db, task, th)
            _maybe_finalize(db, task)
        return {"ok": True, "task_id": task_id, "status": task.status}
    finally:
        db.close()