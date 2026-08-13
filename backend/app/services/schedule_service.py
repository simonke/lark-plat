"""Schedule service: cron/interval tasks, trigger_due for Celery Beat, run history."""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.db.models import ExecTask, ExecTaskHost, ScheduleRun, ScheduleTask
from app.repositories import (
    ExecTaskRepository,
    ExecTaskHostRepository,
    ScheduleRunRepository,
    ScheduleTaskRepository,
)
from app import schemas


def _validate_schedule(data: schemas.ScheduleCreate) -> None:
    if data.kind == "script" and not data.script_id:
        raise BadRequestError("script_id required for kind=script")
    if data.kind == "command" and not data.command:
        raise BadRequestError("command required for kind=command")
    if data.trigger_type == "cron":
        if not data.cron_expr:
            raise BadRequestError("cron_expr required for cron trigger")
        try:
            croniter(data.cron_expr)
        except (ValueError, KeyError) as exc:
            raise BadRequestError(f"invalid cron expression: {exc}")
    elif data.trigger_type == "interval":
        if not data.interval_sec or data.interval_sec < 1:
            raise BadRequestError("interval_sec required for interval trigger")
    else:
        raise BadRequestError("invalid trigger_type")


def _due_tasks(db: Session) -> list[ScheduleTask]:
    repo = ScheduleTaskRepository(db)
    tasks = repo.enabled_tasks()
    now = datetime.now(timezone.utc)
    due = []
    for t in tasks:
        last = db.scalar(
            select(ScheduleRun.started_at).where(ScheduleRun.schedule_task_id == t.id)
            .order_by(ScheduleRun.started_at.desc()).limit(1)
        )
        if t.trigger_type == "interval":
            if last is None or (now - last).total_seconds() >= (t.interval_sec or 0):
                due.append(t)
        elif t.trigger_type == "cron":
            try:
                itr = croniter(t.cron_expr, last or now, ret_type=datetime)
                next_run = itr.get_next(datetime)
                if next_run <= now and (last is None or now >= next_run):
                    due.append(t)
            except Exception:
                continue
    return due


def trigger_due(db: Session) -> int:
    """Create exec tasks for due schedules. Returns number triggered."""
    count = 0
    for sched in _due_tasks(db):
        run_no = f"R-{sched.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        run = ScheduleRun(schedule_task_id=sched.id, run_no=run_no, status="running")
        db.add(run)
        db.flush()
        task = ExecTask(
            task_no=f"SC-{run.id}",
            name=f"[schedule] {sched.name}",
            kind=sched.kind,
            script_id=sched.script_id,
            command=sched.command,
            params=sched.params,
            target_host_ids={"ids": sched.target_host_ids or {}},
            mode="batch",
            timeout_sec=sched.timeout_sec,
            retry=sched.retry,
            status="created",
            created_by=sched.created_by,
        )
        db.add(task)
        db.flush()
        run.task_id = task.id
        # direct dispatch for schedules (no approval in MVP for scheduled ops)
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        try:
            from app.tasks.exec_tasks import exec_dispatch

            exec_dispatch.delay(task.id)
        except Exception:
            pass
        db.commit()
        count += 1
    return count


def list_schedules(db: Session, name: str | None, enabled: int | None, page: int, size: int) -> dict:
    from sqlalchemy import func

    repo = ScheduleTaskRepository(db)
    stmt = select(ScheduleTask)
    if name:
        stmt = stmt.where(ScheduleTask.name.ilike(f"%{name}%"))
    if enabled is not None:
        stmt = stmt.where(ScheduleTask.enabled == enabled)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(ScheduleTask.id.desc()).offset((page - 1) * size).limit(size)).all()
    return {
        "list": [schemas.ScheduleOut.model_validate(r).model_dump() for r in rows],
        "total": int(total), "page": page, "size": size,
    }


def create_schedule(db: Session, user, data: schemas.ScheduleCreate) -> int:
    _validate_schedule(data)
    sched = ScheduleTask(
        **data.model_dump(exclude={"target_host_ids"}),
        target_host_ids={"ids": data.target_host_ids},
        created_by=user.id,
    )
    ScheduleTaskRepository(db).add(sched)
    db.commit()
    return sched.id


def update_schedule(db: Session, schedule_id: int, data: schemas.ScheduleUpdate) -> None:
    repo = ScheduleTaskRepository(db)
    sched = repo.get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    fields = data.model_dump(exclude_none=True)
    if "target_host_ids" in fields:
        sched.target_host_ids = {"ids": fields.pop("target_host_ids")}
    for k, v in fields.items():
        setattr(sched, k, v)
    if sched.trigger_type == "cron":
        try:
            croniter(sched.cron_expr or "")
        except Exception as exc:
            raise BadRequestError(f"invalid cron expression: {exc}")
    db.commit()


def delete_schedule(db: Session, schedule_id: int) -> None:
    repo = ScheduleTaskRepository(db)
    sched = repo.get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    db.delete(sched)
    db.commit()


def set_schedule_status(db: Session, schedule_id: int, enabled: int) -> None:
    repo = ScheduleTaskRepository(db)
    sched = repo.get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    sched.enabled = enabled
    db.commit()


def run_now(db: Session, schedule_id: int) -> dict:
    repo = ScheduleTaskRepository(db)
    sched = repo.get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    run_no = f"R-{sched.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    run = ScheduleRun(schedule_task_id=sched.id, run_no=run_no, status="running")
    db.add(run)
    db.flush()
    task = ExecTask(
        task_no=f"SC-{run.id}",
        name=f"[run-now] {sched.name}",
        kind=sched.kind,
        script_id=sched.script_id,
        command=sched.command,
        params=sched.params,
        target_host_ids={"ids": sched.target_host_ids or {}},
        mode="batch",
        timeout_sec=sched.timeout_sec,
        retry=sched.retry,
        status="running",
        created_by=sched.created_by,
    )
    db.add(task)
    db.flush()
    run.task_id = task.id
    db.commit()
    return {"run_id": run.id, "task_id": task.id, "status": "running"}


def list_runs(db: Session, schedule_id: int, page: int, size: int) -> dict:
    rows, total = ScheduleRunRepository(db).runs_of(schedule_id, page, size)
    return {
        "list": [schemas.ScheduleRunOut.model_validate(r).model_dump() for r in rows],
        "total": total, "page": page, "size": size,
    }


def retry_run(db: Session, schedule_id: int, run_id: int) -> dict:
    repo = ScheduleRunRepository(db)
    run = repo.get(run_id)
    if run is None or run.schedule_task_id != schedule_id:
        raise NotFoundError("run not found")
    sched = ScheduleTaskRepository(db).get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    if run.task_id:
        task_repo = ExecTaskRepository(db)
        task = task_repo.get(run.task_id)
        if task and task.status in ("failed", "timed_out", "canceled"):
            if task_repo.optimistic_update(task.id, task.status, "running", task.version):
                task.version += 1
                task.started_at = datetime.now(timezone.utc)
                db.commit()
                return {"task_id": task.id, "status": "running"}
    # no prior task -> rerun now
    return run_now(db, schedule_id)
