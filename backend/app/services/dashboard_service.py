"""Dashboard service: stats, task trend, recent tasks/approvals (US-08 dashboard module)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ApprovalRequest, ExecTask, Host
from app.repositories import HostRepository


def _visible_host_ids(db: Session, user) -> list[int] | None:
    if user.is_admin:
        return None
    ids = user.visible_group_ids
    if not ids:
        return []  # default deny
    return list(db.scalars(select(Host.id).where(Host.group_id.in_(ids))).all())


def stats(db: Session, user) -> dict:
    host_ids = _visible_host_ids(db, user)
    host_stmt = select(Host)
    if host_ids is not None:
        host_stmt = host_stmt.where(Host.id.in_(host_ids))
    hosts = list(db.scalars(host_stmt).all())
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    tasks_stmt = select(ExecTask)
    if not user.is_admin:
        tasks_stmt = tasks_stmt.where(ExecTask.created_by == user.id)
    tasks = list(db.scalars(tasks_stmt).all())
    running = [t for t in tasks if t.status == "running"]
    today = [t for t in tasks if t.created_at and t.created_at >= today_start]
    today_success = [t for t in today if t.status == "success"]
    pending = db.scalar(select(func.count()).select_from(ApprovalRequest).where(
        ApprovalRequest.status == "pending")) or 0
    return {
        "host_total": len(hosts),
        "host_online": sum(1 for h in hosts if h.status == "online"),
        "tasks_running": len(running),
        "today_tasks": len(today),
        "today_success": len(today_success),
        "pending_approvals": int(pending),
    }


def task_trend(db: Session, user, days: int) -> list[dict]:
    out: list[dict] = []
    now = datetime.now(timezone.utc)
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        stmt = select(ExecTask).where(ExecTask.created_at >= start, ExecTask.created_at < end)
        if not user.is_admin:
            stmt = stmt.where(ExecTask.created_by == user.id)
        rows = list(db.scalars(stmt).all())
        out.append({
            "date": day.isoformat(),
            "total": len(rows),
            "success": sum(1 for r in rows if r.status == "success"),
            "failed": sum(1 for r in rows if r.status in ("failed", "timed_out")),
        })
    return out


def recent_tasks(db: Session, user) -> list[dict]:
    stmt = select(ExecTask).order_by(ExecTask.id.desc()).limit(10)
    if not user.is_admin:
        stmt = stmt.where(ExecTask.created_by == user.id)
    rows = db.scalars(stmt).all()
    return [{
        "id": t.id, "task_no": t.task_no, "name": t.name, "status": t.status, "kind": t.kind,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    } for t in rows]


def recent_approvals(db: Session, user) -> list[dict]:
    stmt = select(ApprovalRequest).order_by(ApprovalRequest.id.desc()).limit(10)
    if not user.is_admin:
        stmt = stmt.where(ApprovalRequest.requester_id == user.id)
    rows = db.scalars(stmt).all()
    return [{
        "id": a.id, "request_no": a.request_no, "title": a.title, "status": a.status,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in rows]
