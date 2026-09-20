"""Executor orchestration — the additive P2-SS execution path.

Gate order is shared with the agent path and frozen:

    approval gate -> sensitivity gate -> executor.exec() -> exec_log write

The gates and the log writer reuse the SAME existing symbols as the agent path
(``exec_service.detect_sensitive`` / ``ExecLogRepository.append``); this module
does not modify the agent code. It is entered by ``connector == "ssh"``.

The skeleton performs no real SSH: ``SSHExecutor.exec`` degrades with
``NotImplementedError`` when ``paramiko`` is absent, and the orchestration still
runs both gates first and records a degraded ``exec_log`` row (so gate order and
the ``exec_log`` shape are assertable offline).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ExecTask, ExecTaskHost
from app.repositories import ApprovalRepository, ExecLogRepository
from app.services.executors import build_executor

logger = logging.getLogger(__name__)

APPROVED = "approved"


def _approval_gate(db: Session, task: ExecTask) -> str | None:
    """Return a skip reason when the task has not cleared its approval gate."""
    if not task.approve_required:
        return None
    approval = (
        ApprovalRepository(db).get(task.approval_id) if task.approval_id else None
    )
    if approval is not None and approval.status == APPROVED:
        return None
    return "awaiting approval"


def _sensitivity_gate(
    db: Session, task: ExecTask, content: str, host_count: int
) -> str | None:
    """Reuse the agent path's sensitive detector (same symbol)."""
    from app.services.exec_service import detect_sensitive

    sensitive, reason = detect_sensitive(db, task.command, content, host_count)
    if sensitive:
        return f"sensitive operation: {reason}"
    return None


def _write_log(db: Session, th: ExecTaskHost, level: str, content: str) -> None:
    """Append via the agent path's exec_log writer (same symbol/table)."""
    repo = ExecLogRepository(db)
    repo.append(th.id, repo.max_seq(th.id) + 1, level, content)
    db.commit()


def run_exec(
    db: Session,
    task: ExecTask,
    th: ExecTaskHost,
    content: str,
    *,
    host_count: int = 1,
    executor: Any | None = None,
) -> dict[str, Any]:
    """Run one host through the frozen gate order, then the executor.

    ``executor`` is the injection seam: it defaults to the registry lookup for
    ``th.executor`` and may be passed directly, or ``build_executor`` may be
    monkeypatched, so a fake with ``available=True/False`` can be injected.
    """
    skip = _approval_gate(db, task)
    if skip is None:
        skip = _sensitivity_gate(db, task, content, host_count)
    if skip is not None:
        _write_log(db, th, "warn", f"[executor:{th.executor}] skipped: {skip}")
        return {"ok": False, "detail": skip, "skipped": True}

    ex = executor if executor is not None else build_executor(th.executor)
    try:
        result = ex.exec(db=db, task=task, host=th, content=content)
    except NotImplementedError as exc:
        # Skeleton / soft-dep path: paramiko missing -> degraded, still logged.
        result = {"ok": False, "degraded": True, "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - dispatch must not crash on one host
        logger.warning("executor %s failed: %s", th.executor, exc)
        result = {"ok": False, "degraded": True, "detail": f"executor error: {exc}"}

    level = "info" if result.get("ok") else "error"
    _write_log(db, th, level, f"[executor:{th.executor}] {result.get('detail', '')}")
    return result
