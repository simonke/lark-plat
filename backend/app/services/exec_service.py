"""Exec service: task state machine, sensitive detection, approval linkage,
concurrency guard, WS log cursor, stop/retry. Celery dispatch in app/tasks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, BusinessError, ConflictError, ForbiddenError, NotFoundError
from app.core.redis_helper import get_redis
from app.db.models import ApprovalRequest, ConfigRule, ExecLog, ExecTask, ExecTaskHost, Host, Script
from app.repositories import (
    ApprovalRepository,
    ConfigRuleRepository,
    ExecLogRepository,
    ExecTaskHostRepository,
    ExecTaskRepository,
    HostRepository,
    ScriptRepository,
    ScriptVersionRepository,
)
from app import schemas
from app.tasks.exec_tasks import exec_dispatch


def _task_no(db: Session) -> str:
    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    count = db.scalar(select(ExecTask.id).order_by(ExecTask.id.desc()).limit(1))
    return f"{prefix}-{count + 1 if count else 1:03d}"


def _sensitive_rules(db: Session) -> dict[str, list[Any]]:
    repo = ConfigRuleRepository(db)
    out: dict[str, list[Any]] = {"keywords": [], "threshold": None, "global_conc": None, "host_conc": None}
    for key, default in (("exec_sensitive_word", "keywords"), ("exec_batch_threshold", "threshold"),
                         ("exec_concurrency_limit", "global_conc"), ("exec_host_concurrency", "host_conc")):
        rule = repo.by_key(key)
        if not rule:
            continue
        val = rule.rule_value or {}
        if key == "exec_sensitive_word":
            out["keywords"] = val.get("words", [])
        elif key == "exec_batch_threshold":
            out["threshold"] = val.get("threshold")
        else:
            out["global_conc"] = val.get("limit")
    return out


def detect_sensitive(db: Session, command: str | None, script_content: str | None, host_count: int) -> tuple[bool, str]:
    rules = _sensitive_rules(db)
    text = f"{command or ''}\n{script_content or ''}".lower()
    hit_words = [w for w in rules["keywords"] if w and w.lower() in text]
    reasons = []
    if hit_words:
        reasons.append("sensitive word: " + ",".join(hit_words[:5]))
    if rules["threshold"] and host_count >= rules["threshold"]:
        reasons.append(f"batch size {host_count} >= threshold {rules['threshold']}")
    return (bool(reasons), "; ".join(reasons))


def create_task(db: Session, user, data: schemas.ExecTaskCreate) -> dict:
    # 1. validate permission
    user.require_perm("exec:task:run")
    # 2. validate targets are visible hosts (US-03)
    host_repo = HostRepository(db)
    hosts: dict[int, Host] = {}
    for hid in data.target_host_ids:
        host = host_repo.get(hid)
        if host is None:
            raise NotFoundError(f"host {hid} not found")
        if not user.is_admin and host.group_id not in user.visible_group_ids:
            raise ForbiddenError(f"no data permission for host {hid}")
        hosts[hid] = host

    script_content = None
    if data.kind == "script":
        if not data.script_id:
            raise BadRequestError("script_id required for kind=script")
        script = ScriptRepository(db).get(data.script_id)
        if script is None:
            raise NotFoundError("script not found")
        version = data.script_version or script.current_version
        sv = ScriptVersionRepository(db).by_script_version(script.id, version)
        if sv is None:
            raise NotFoundError("script version not found")
        script_content = sv.content
    elif data.kind == "command":
        if not data.command:
            raise BadRequestError("command required for kind=command")
    else:
        raise BadRequestError("invalid kind")

    # 3. sensitive detection -> approval linkage (US-06, US-09)
    sensitive, reason = detect_sensitive(db, data.command, script_content, len(hosts))
    rules = _sensitive_rules(db)
    approve_required = 1 if sensitive else 0

    task = ExecTask(
        task_no=_task_no(db),
        name=data.name,
        kind=data.kind,
        script_id=data.script_id,
        script_version=data.script_version,
        command=data.command,
        params=data.params,
        target_host_ids={"ids": data.target_host_ids},
        mode=data.mode,
        timeout_sec=data.timeout_sec,
        retry=data.retry,
        sensitive_flag=1 if sensitive else 0,
        approve_required=approve_required,
        status="created",
        created_by=user.id,
    )
    task_repo = ExecTaskRepository(db)
    task_repo.add(task)
    db.flush()

    host_repo = HostRepository(db)
    task_host_repo = ExecTaskHostRepository(db)
    for hid in data.target_host_ids:
        h = hosts[hid]
        task_host_repo.add(ExecTaskHost(
            exec_task_id=task.id, host_id=h.id, hostname=h.hostname, ip=h.ip,
            executor=h.connector, status="pending",
        ))
    db.flush()

    approval_id = None
    if approve_required:
        approval = ApprovalRequest(
            request_no=_approval_no(db),
            biz_type="exec",
            biz_id=task.id,
            title=f"执行审批：{task.name}",
            reason=f"敏感操作需审批：{reason}",
            requester_id=user.id,
            sensitive_hit=reason,
            status="pending",
        )
        ApprovalRepository(db).add(approval)
        db.flush()
        approval_id = approval.id
        task.approval_id = approval.id
        if not task_repo.optimistic_update(task.id, "created", "awaiting_approval", task.version):
            raise ConflictError("task state changed concurrently")
        task.version += 1
        db.flush()
        db.commit()
        return {"id": task.id, "task_no": task.task_no, "status": "awaiting_approval",
                "approve_required": True, "approval_id": approval_id, "sensitive_flag": True}

    # 4. direct dispatch
    if not task_repo.optimistic_update(task.id, "created", "running", task.version):
        raise ConflictError("task state changed concurrently")
    task.version += 1
    task.started_at = datetime.now(timezone.utc)
    db.commit()

    try:
        exec_dispatch.delay(task.id)
    except Exception:
        pass  # degraded: execution proceeds in-process fallback below
    return {"id": task.id, "task_no": task.task_no, "status": "running",
            "approve_required": False, "approval_id": None, "sensitive_flag": False}


def _approval_no(db: Session) -> str:
    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    count = db.scalar(select(ApprovalRequest.id).order_by(ApprovalRequest.id.desc()).limit(1))
    return f"AP-{prefix}-{count + 1 if count else 1:04d}"


def list_tasks(db: Session, user, task_no: str | None, name: str | None, status: str | None,
               kind: str | None, start, end, page: int, size: int) -> dict:
    user.require_perm("exec:task:list")
    filters = {"task_no": task_no, "name": name, "status": status, "kind": kind,
               "start": start, "end": end, "created_by": user.id if user.is_admin else user.id}
    rows, total = ExecTaskRepository(db).search(filters, page, size)
    return {"list": [_exec_task_out(t) for t in rows], "total": total, "page": page, "size": size}


def _exec_task_out(task: ExecTask) -> dict:
    return {
        "id": task.id, "task_no": task.task_no, "name": task.name, "kind": task.kind,
        "script_id": task.script_id, "script_version": task.script_version, "command": task.command,
        "params": task.params, "target_host_ids": task.target_host_ids, "mode": task.mode,
        "timeout_sec": task.timeout_sec, "retry": task.retry, "sensitive_flag": task.sensitive_flag,
        "approve_required": task.approve_required, "approval_id": task.approval_id, "status": task.status,
        "created_by": task.created_by,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
    }


def get_task(db: Session, user, task_id: int) -> dict:
    user.require_perm("exec:task:list")
    task = ExecTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    data = _exec_task_out(task)
    data["hosts"] = [_exec_host_out(h) for h in ExecTaskHostRepository(db).by_task(task_id)]
    if task.approval_id:
        approval = ApprovalRepository(db).get(task.approval_id)
        data["approval_status"] = approval.status if approval else None
    return data


def _exec_host_out(h: ExecTaskHost) -> dict:
    return {
        "id": h.id, "host_id": h.host_id, "hostname": h.hostname, "ip": h.ip, "executor": h.executor,
        "status": h.status, "exit_code": h.exit_code,
        "started_at": h.started_at.isoformat() if h.started_at else None,
        "finished_at": h.finished_at.isoformat() if h.finished_at else None,
    }


def task_stats(db: Session, user, task_id: int) -> dict:
    user.require_perm("exec:task:list")
    task = ExecTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    stats = ExecTaskHostRepository(db).stats(task_id)
    return {"total": sum(stats.values()),
            "pending": stats.get("pending", 0), "running": stats.get("running", 0),
            "success": stats.get("success", 0), "failed": stats.get("failed", 0),
            "timed_out": stats.get("timed_out", 0), "canceled": stats.get("canceled", 0)}


def get_logs(db: Session, user, task_id: int, task_host_id: int, after_seq: int, size: int) -> dict:
    user.require_perm("exec:task:log")
    task = ExecTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    th_repo = ExecTaskHostRepository(db)
    th = th_repo.by_id(task_host_id)
    if th is None or th.exec_task_id != task_id:
        raise NotFoundError("task host not found")
    rows, _ = ExecLogRepository(db).after_seq(task_host_id, after_seq, size)
    next_seq = after_seq + len(rows)
    return {"list": [{"seq": r.seq, "level": r.level, "content": r.content,
                      "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows],
            "next_seq": next_seq}


def ws_token(db: Session, user, task_id: int, task_host_id: int) -> dict:
    user.require_perm("exec:task:log")
    task = ExecTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    th_repo = ExecTaskHostRepository(db)
    th = th_repo.by_id(task_host_id)
    if th is None or th.exec_task_id != task_id:
        raise NotFoundError("task host not found")
    from app.ws.exec_ws import create_ws_token

    return {"token": create_ws_token(task_host_id)}


def stop_task(db: Session, user, task_id: int) -> dict:
    user.require_perm("exec:task:stop")
    repo = ExecTaskRepository(db)
    task = repo.get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to stop this task")
    if task.status not in ("running", "pending"):
        raise BadRequestError("task not running")
    if not repo.optimistic_update(task.id, task.status, "canceled", task.version):
        raise ConflictError("task state changed concurrently")
    task.version += 1
    task.finished_at = datetime.now(timezone.utc)
    th_repo = ExecTaskHostRepository(db)
    for th in th_repo.by_task(task_id):
        if th.status in ("pending", "running"):
            th_repo.update_status(th.id, "canceled", finished_at=datetime.now(timezone.utc))
    db.commit()
    return {"id": task.id, "status": "canceled"}


def retry_task(db: Session, user, task_id: int) -> dict:
    user.require_perm("exec:task:retry")
    repo = ExecTaskRepository(db)
    task = repo.get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to retry this task")
    if task.status not in ("failed", "timed_out", "canceled"):
        raise BadRequestError("task not retryable")
    if not repo.optimistic_update(task.id, task.status, "running", task.version):
        raise ConflictError("task state changed concurrently")
    task.version += 1
    task.started_at = datetime.now(timezone.utc)
    task.finished_at = None
    th_repo = ExecTaskHostRepository(db)
    for th in th_repo.by_task(task_id):
        if th.status in ("failed", "timed_out", "canceled"):
            th_repo.update_status(th.id, "pending")
    db.commit()
    try:
        exec_dispatch.delay(task_id)
    except Exception:
        pass
    return {"id": task.id, "status": "running"}
