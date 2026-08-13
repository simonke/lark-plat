"""Approval service: state machine, idempotent submit (biz_id unique), optimistic lock,
exec linkage (approve -> unfreeze & dispatch; reject -> cancel task). US-06/09."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.db.models import ApprovalRecord, ApprovalRequest, ApprovalRule, ExecTask
from app.repositories import (
    ApprovalRecordRepository,
    ApprovalRepository,
    ApprovalRuleRepository,
    ExecTaskRepository,
)
from app import schemas


def _approval_no(db: Session) -> str:
    from sqlalchemy import select

    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    count = db.scalar(select(ApprovalRequest.id).order_by(ApprovalRequest.id.desc()).limit(1))
    return f"AP-{prefix}-{count + 1 if count else 1:04d}"


def list_approvals(db: Session, user, status: str | None, biz_type: str | None, mine: bool,
                   todo: bool, page: int, size: int) -> dict:
    filters: dict = {"status": status, "biz_type": biz_type}
    if mine:
        filters["requester_id"] = user.id
    if todo:
        filters["mine_todo"] = True
    rows, total = ApprovalRepository(db).search(filters, page, size)
    return {
        "list": [_approval_out(r) for r in rows],
        "total": total, "page": page, "size": size,
    }


def _approval_out(a: ApprovalRequest) -> dict:
    return {
        "id": a.id, "request_no": a.request_no, "biz_type": a.biz_type, "biz_id": a.biz_id,
        "title": a.title, "reason": a.reason, "requester_id": a.requester_id,
        "sensitive_hit": a.sensitive_hit, "status": a.status, "approver_id": a.approver_id,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "version": a.version,
    }


def detail(db: Session, approval_id: int) -> dict:
    repo = ApprovalRepository(db)
    a = repo.get(approval_id)
    if a is None:
        raise NotFoundError("approval not found")
    data = _approval_out(a)
    data["timeline"] = [
        {"action": r.action, "operator_id": r.operator_id, "comment": r.comment,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in ApprovalRecordRepository(db).timeline(approval_id)
    ]
    return data


def _require_pending(db: Session, approval_id: int, user) -> ApprovalRequest:
    repo = ApprovalRepository(db)
    a = repo.get(approval_id)
    if a is None:
        raise NotFoundError("approval not found")
    if a.status != "pending":
        raise ConflictError("approval already decided")
    return a


def _approve_exec(db: Session, a: ApprovalRequest) -> None:
    """Approve -> exec_task approved -> running -> dispatch. Enforced at exec entry (cannot bypass)."""
    task_repo = ExecTaskRepository(db)
    task = task_repo.get(a.biz_id)
    if task is None:
        raise NotFoundError("linked exec task not found")
    if not task_repo.optimistic_update(task.id, "awaiting_approval", "running", task.version):
        raise ConflictError("exec task state changed concurrently")
    task.version += 1
    task.started_at = datetime.now(timezone.utc)
    try:
        from app.tasks.exec_tasks import exec_dispatch

        exec_dispatch.delay(task.id)
    except Exception:
        pass


def approve(db: Session, user, approval_id: int, comment: str) -> dict:
    user.require_perm("approval:approve")
    repo = ApprovalRepository(db)
    a = _require_pending(db, approval_id, user)
    if not repo.optimistic_update(a.id, "pending", "approved", a.version):
        raise ConflictError("approval modified concurrently, refresh and retry")
    a.version += 1
    a.approver_id = user.id
    a.decided_at = datetime.now(timezone.utc)
    db.add(ApprovalRecord(approval_id=a.id, action="approve", operator_id=user.id, comment=comment))
    db.flush()
    try:
        _approve_exec(db, a)
    except (NotFoundError, ConflictError):
        db.rollback()
        raise
    db.commit()
    return {"id": a.id, "status": "approved"}


def reject(db: Session, user, approval_id: int, comment: str) -> dict:
    user.require_perm("approval:approve")
    repo = ApprovalRepository(db)
    a = _require_pending(db, approval_id, user)
    if not repo.optimistic_update(a.id, "pending", "rejected", a.version):
        raise ConflictError("approval modified concurrently, refresh and retry")
    a.version += 1
    a.approver_id = user.id
    a.decided_at = datetime.now(timezone.utc)
    db.add(ApprovalRecord(approval_id=a.id, action="reject", operator_id=user.id, comment=comment))
    task_repo = ExecTaskRepository(db)
    task = task_repo.get(a.biz_id)
    if task and task.status == "awaiting_approval":
        if task_repo.optimistic_update(task.id, "awaiting_approval", "canceled", task.version):
            task.version += 1
            task.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": a.id, "status": "rejected"}


def cancel(db: Session, user, approval_id: int) -> dict:
    repo = ApprovalRepository(db)
    a = _require_pending(db, approval_id, user)
    if a.requester_id != user.id and not user.is_admin:
        raise ForbiddenError("only requester can cancel")
    if not repo.optimistic_update(a.id, "pending", "canceled", a.version):
        raise ConflictError("approval modified concurrently, refresh and retry")
    a.version += 1
    a.decided_at = datetime.now(timezone.utc)
    db.add(ApprovalRecord(approval_id=a.id, action="cancel", operator_id=user.id, comment="requester cancel"))
    task_repo = ExecTaskRepository(db)
    task = task_repo.get(a.biz_id)
    if task and task.status == "awaiting_approval":
        if task_repo.optimistic_update(task.id, "awaiting_approval", "canceled", task.version):
            task.version += 1
            task.finished_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": a.id, "status": "canceled"}


# ---------------------------------------------------------------- rules


def list_rules(db: Session) -> list[dict]:
    return [
        schemas.RuleOut.model_validate(r).model_dump()
        for r in ApprovalRuleRepository(db).enabled() or ApprovalRuleRepository(db).list_all()
    ]


def create_rule(db: Session, data: schemas.RuleCreate) -> int:
    if data.kind not in ("keyword", "count"):
        raise BadRequestError("invalid rule kind")
    rule = ApprovalRule(**data.model_dump())
    ApprovalRuleRepository(db).add(rule)
    db.commit()
    return rule.id


def update_rule(db: Session, rule_id: int, data: schemas.RuleUpdate) -> None:
    repo = ApprovalRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None:
        raise NotFoundError("rule not found")
    if data.name is not None:
        rule.name = data.name
    if data.value is not None:
        rule.value = data.value
    if data.enabled is not None:
        rule.enabled = data.enabled
    db.commit()


def delete_rule(db: Session, rule_id: int) -> None:
    repo = ApprovalRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None:
        raise NotFoundError("rule not found")
    db.delete(rule)
    db.commit()
