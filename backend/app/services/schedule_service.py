"""Schedule service: cron/interval tasks, trigger_due for Celery Beat, run history."""

from __future__ import annotations

from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.db.models import ApprovalRequest, ExecTask, ExecTaskHost, Host, ScheduleRun, ScheduleTask
from app.repositories import (
    ApprovalRepository,
    ExecTaskRepository,
    ExecTaskHostRepository,
    HostRepository,
    ScheduleRunRepository,
    ScheduleTaskRepository,
    ScriptRepository,
    ScriptVersionRepository,
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


def _run_no(schedule_id: int) -> str:
    return f"R-{schedule_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _spawn_run(db: Session, sched: ScheduleTask, requester_id: int, name_prefix: str) -> dict:
    """Create ScheduleRun + ExecTask + ExecTaskHost for a schedule invocation.

    US-08 item 7 / §12.8: sensitivity is re-validated with the exec rules
    (keywords, batch threshold, host set). Sensitive runs go through the
    biz_type=exec approval chain - approval may never be bypassed for
    scheduled ops (incl. run-now / retry). Non-sensitive runs dispatch
    directly like exec create_task.
    """
    from app.services.exec_service import _kick_off_exec, detect_sensitive  # lazy: avoid task/service cycle

    host_ids = list((sched.target_host_ids or {}).get("ids", []))
    host_repo = HostRepository(db)
    hosts: dict[int, Host] = {}
    for hid in host_ids:
        host = host_repo.get(hid)
        if host is None:
            raise NotFoundError(f"host {hid} not found")
        hosts[hid] = host

    script_content = None
    script_version = None
    if sched.kind == "script":
        if not sched.script_id:
            raise BadRequestError("script_id required for kind=script")
        script = ScriptRepository(db).get(sched.script_id)
        if script is None:
            raise NotFoundError("script not found")
        sv = ScriptVersionRepository(db).by_script_version(script.id, script.current_version)
        if sv is None:
            raise NotFoundError("script version not found")
        script_content = sv.content
        script_version = script.current_version
    elif sched.kind == "command":
        if not sched.command:
            raise BadRequestError("command required for kind=command")
    else:
        raise BadRequestError("invalid kind")

    sensitive, reason = detect_sensitive(db, sched.command, script_content, len(hosts))

    run = ScheduleRun(schedule_task_id=sched.id, run_no=_run_no(sched.id), status="running")
    db.add(run)
    db.flush()

    task = ExecTask(
        task_no=f"SC-{run.id}",
        name=f"{name_prefix} {sched.name}",
        kind=sched.kind,
        script_id=sched.script_id,
        script_version=script_version,
        command=sched.command,
        params=sched.params,
        target_host_ids={"ids": host_ids},
        mode="batch",
        timeout_sec=sched.timeout_sec,
        retry=sched.retry,
        sensitive_flag=1 if sensitive else 0,
        approve_required=1 if sensitive else 0,
        status="created",
        created_by=requester_id,
    )
    task_repo = ExecTaskRepository(db)
    task_repo.add(task)
    db.flush()

    th_repo = ExecTaskHostRepository(db)
    for hid in host_ids:
        h = hosts[hid]
        th_repo.add(ExecTaskHost(
            exec_task_id=task.id, host_id=h.id, hostname=h.hostname, ip=h.ip,
            executor=h.connector, status="pending",
        ))
    db.flush()
    run.task_id = task.id

    if sensitive:
        from app.services.exec_service import _approval_no

        approval = ApprovalRequest(
            request_no=_approval_no(db),
            biz_type="exec",
            biz_id=task.id,
            title=f"执行审批：{task.name}",
            reason=f"定时任务敏感操作需审批：{reason}",
            requester_id=requester_id,
            sensitive_hit=reason,
            status="pending",
        )
        ApprovalRepository(db).add(approval)
        db.flush()
        task.approval_id = approval.id
        if not task_repo.optimistic_update(task.id, "created", "awaiting_approval", task.version):
            raise ConflictError("task state changed concurrently")
        task.version += 1
        db.commit()
        return {"run_id": run.id, "task_id": task.id, "status": "awaiting_approval",
                "approve_required": True, "approval_id": approval.id, "sensitive_flag": True}

    if not task_repo.optimistic_update(task.id, "created", "running", task.version):
        raise ConflictError("task state changed concurrently")
    task.version += 1
    task.started_at = datetime.now(timezone.utc)
    db.commit()
    _kick_off_exec(db, task.id)
    return {"run_id": run.id, "task_id": task.id, "status": "running",
            "approve_required": False, "approval_id": None, "sensitive_flag": False}


def trigger_due(db: Session) -> int:
    """Create exec tasks for due schedules. Returns number triggered.

    A failing schedule is recorded on its ScheduleRun (error_msg) so one broken
    schedule never aborts the whole beat sweep. Sensitive due runs wait for
    approval instead of dispatching directly.
    """
    count = 0
    for sched in _due_tasks(db):
        try:
            _spawn_run(db, sched, sched.created_by or 0, "[schedule]")
            count += 1
        except Exception as exc:  # noqa: BLE001 - sweep must continue
            db.rollback()
            run = ScheduleRun(schedule_task_id=sched.id, run_no=_run_no(sched.id),
                              status="failed", error_msg=str(exc)[:500])
            db.add(run)
            try:
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
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


def run_now(db: Session, user, schedule_id: int) -> dict:
    repo = ScheduleTaskRepository(db)
    sched = repo.get(schedule_id)
    if sched is None:
        raise NotFoundError("schedule not found")
    return _spawn_run(db, sched, user.id, "[run-now]")


def list_runs(db: Session, schedule_id: int, page: int, size: int) -> dict:
    rows, total = ScheduleRunRepository(db).runs_of(schedule_id, page, size)
    return {
        "list": [schemas.ScheduleRunOut.model_validate(r).model_dump() for r in rows],
        "total": total, "page": page, "size": size,
    }


def retry_run(db: Session, user, schedule_id: int, run_id: int) -> dict:
    from app.services.exec_service import _approval_no, _close_orphan_approval, _kick_off_exec, detect_sensitive

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
            # US-08 item 7 / G8: retry re-validates sensitivity (config may have
            # changed) and closes any orphaned approval before dispatch.
            content = task.command or ""
            if task.kind == "script" and task.script_id:
                script = ScriptRepository(db).get(task.script_id)
                if script is not None:
                    version = task.script_version or script.current_version
                    sv = ScriptVersionRepository(db).by_script_version(script.id, version)
                    content = sv.content if sv else ""
            host_count = len((task.target_host_ids or {}).get("ids", []))
            sensitive, reason = detect_sensitive(db, task.command, content, host_count)
            if sensitive:
                if not task_repo.optimistic_update(task.id, task.status, "awaiting_approval", task.version):
                    raise ConflictError("task state changed concurrently")
                task.version += 1
                _close_orphan_approval(db, task)
                approval = ApprovalRequest(
                    request_no=_approval_no(db),
                    biz_type="exec",
                    biz_id=task.id,
                    title=f"执行审批：{task.name}",
                    reason=f"重试触发敏感复检：{reason}",
                    requester_id=user.id,
                    sensitive_hit=reason,
                    status="pending",
                )
                ApprovalRepository(db).add(approval)
                db.flush()
                task.approval_id = approval.id
                task.sensitive_flag = 1
                run.status = "running"
                run.finished_at = None
                db.commit()
                return {"run_id": run.id, "task_id": task.id, "status": "awaiting_approval",
                        "approve_required": True, "approval_id": approval.id, "sensitive_flag": True}
            if not task_repo.optimistic_update(task.id, task.status, "running", task.version):
                raise ConflictError("task state changed concurrently")
            task.version += 1
            task.started_at = datetime.now(timezone.utc)
            task.finished_at = None
            _close_orphan_approval(db, task)
            th_repo = ExecTaskHostRepository(db)
            for th in th_repo.by_task(task.id):
                if th.status in ("failed", "timed_out", "canceled"):
                    th_repo.update_status(th.id, "pending")
            run.status = "running"
            run.finished_at = None
            db.commit()
            _kick_off_exec(db, task.id)
            return {"run_id": run.id, "task_id": task.id, "status": "running"}
    # no prior task -> rerun now
    return _spawn_run(db, sched, user.id, "[retry]")
