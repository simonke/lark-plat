"""Ticket service (P3-1): lifecycle state machine + comments/attachments/refs.

Frozen contract:
  - ``TICKET_TRANSITIONS`` is action-keyed: action -> (allowed_from, target)
    (架构 seq2605 §三; ordering of allowed_from is NOT part of the contract).
  - POST /tickets with ``assignee_id`` needs BOTH ``ticket:create`` AND
    ``ticket:assign`` => 403 otherwise; without assignee the status is ``create``.
  - edit is allowed only while status ∈ TICKET_EDITABLE_STATUSES (pre-accept).
  - refs duplicate ``(ticket_id, ref_type, ref_id)`` is idempotent (200).
  - feature flag ``feature.ticket`` gates behavior (default False -> 400).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import schemas
from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError, ValidationError
from app.db.models import FilePackage, Ticket, TicketAttachment, TicketComment, TicketRef
from app.db.models.ticket import (
    TICKET_CATEGORIES,
    TICKET_EDITABLE_STATUSES,
    TICKET_PRIORITIES,
    TICKET_REF_TYPES,
)
from app.repositories import ConfigRuleRepository

# action -> (allowed_from, target_status) — frozen shape (seq2605 §三).
TICKET_TRANSITIONS = {
    "assign": (("create", "assign"), "assign"),
    "accept": (("assign",), "accept"),
    "process": (("accept",), "processing"),
    "done": (("processing",), "done"),
    "close": (("done",), "close"),
    "reopen": (("done", "close"), "processing"),
    "cancel": (("create", "assign", "accept", "processing"), "cancel"),
}


def _require_feature(db: Session) -> None:
    """feature.ticket gates behavior (not routes); default False => 400."""
    rule = ConfigRuleRepository(db).by_key("feature.ticket")
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")


def _get(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("ticket not found")
    return ticket


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _out(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "title": ticket.title,
        "category": ticket.category,
        "priority": ticket.priority,
        "status": ticket.status,
        "requester_id": ticket.requester_id,
        "assignee_id": ticket.assignee_id,
        "team_id": ticket.team_id,
        "description": ticket.description,
        "sla_due_at": _iso(ticket.sla_due_at),
        "resolved_at": _iso(ticket.resolved_at),
        "closed_at": _iso(ticket.closed_at),
        "version": ticket.version,
        "created_at": _iso(ticket.created_at),
        "updated_at": _iso(ticket.updated_at),
    }


def _apply_transition(ticket: Ticket, action: str) -> str:
    allowed_from, target = TICKET_TRANSITIONS[action]
    if ticket.status not in allowed_from:
        raise BadRequestError(f"cannot {action} ticket in status '{ticket.status}'")
    ticket.status = target
    ticket.version += 1
    return target


# =============================================================== CRUD


def create_ticket(db: Session, user, data: schemas.TicketCreate) -> dict:
    _require_feature(db)
    user.require_perm("ticket:create")
    if data.category not in TICKET_CATEGORIES:
        raise ValidationError(f"invalid category: {data.category}")
    if data.priority not in TICKET_PRIORITIES:
        raise ValidationError(f"invalid priority: {data.priority}")

    status = "create"
    if data.assignee_id:
        # ⑥: creating straight into 'assign' needs ticket:assign too.
        user.require_perm("ticket:assign")
        status = "assign"

    ticket = Ticket(
        title=data.title,
        category=data.category,
        priority=data.priority,
        status=status,
        requester_id=user.id,
        assignee_id=data.assignee_id,
        description=data.description or "",
        sla_due_at=data.due_at,
        version=0,
    )
    db.add(ticket)
    db.flush()
    for host_id in data.host_ids or []:
        db.add(TicketRef(ticket_id=ticket.id, ref_type="asset_host", ref_id=host_id,
                         created_by=user.id))
    db.commit()
    return _out(ticket)


def list_tickets(db: Session, user, filters: dict, page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("ticket:list")
    stmt = select(Ticket)
    conds = []
    for key in ("category", "status", "priority"):
        if filters.get(key):
            conds.append(getattr(Ticket, key) == filters[key])
    if filters.get("requester_id"):
        conds.append(Ticket.requester_id == filters["requester_id"])
    if filters.get("assignee_id"):
        conds.append(Ticket.assignee_id == filters["assignee_id"])
    if filters.get("start"):
        conds.append(Ticket.created_at >= filters["start"])
    if filters.get("end"):
        conds.append(Ticket.created_at <= filters["end"])
    if conds:
        stmt = stmt.where(*conds)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Ticket.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return {"list": [_out(r) for r in rows], "total": int(total), "page": page, "size": size}


def get_ticket(db: Session, user, ticket_id: int) -> dict:
    _require_feature(db)
    user.require_perm("ticket:list")
    ticket = _get(db, ticket_id)
    refs = db.scalars(
        select(TicketRef).where(TicketRef.ticket_id == ticket_id).order_by(TicketRef.id)
    ).all()
    comments = db.scalars(
        select(TicketComment).where(TicketComment.ticket_id == ticket_id)
        .order_by(TicketComment.id)
    ).all()
    attachments = db.scalars(
        select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)
        .order_by(TicketAttachment.id)
    ).all()
    out = _out(ticket)
    out["refs"] = [
        {"id": r.id, "ref_type": r.ref_type, "ref_id": r.ref_id} for r in refs
    ]
    out["comments"] = [
        {"id": c.id, "author_id": c.author_id, "content": c.content,
         "created_at": _iso(c.created_at)} for c in comments
    ]
    out["attachments"] = [
        {"id": a.id, "file_id": a.file_id, "filename": a.filename, "size": a.size,
         "created_at": _iso(a.created_at)} for a in attachments
    ]
    return out


def edit_ticket(db: Session, user, ticket_id: int, data: schemas.TicketUpdate) -> dict:
    _require_feature(db)
    user.require_perm("ticket:edit")
    ticket = _get(db, ticket_id)
    if ticket.status not in TICKET_EDITABLE_STATUSES:
        raise BadRequestError(
            f"ticket not editable in status '{ticket.status}'"
        )
    if data.title is not None:
        ticket.title = data.title
    if data.category is not None:
        if data.category not in TICKET_CATEGORIES:
            raise ValidationError(f"invalid category: {data.category}")
        ticket.category = data.category
    if data.priority is not None:
        if data.priority not in TICKET_PRIORITIES:
            raise ValidationError(f"invalid priority: {data.priority}")
        ticket.priority = data.priority
    if data.description is not None:
        ticket.description = data.description
    if data.assignee_id is not None:
        ticket.assignee_id = data.assignee_id
    if data.due_at is not None:
        ticket.sla_due_at = data.due_at
    ticket.version += 1
    db.commit()
    return _out(ticket)


# =============================================================== transitions


def assign_ticket(db: Session, user, ticket_id: int, data: schemas.TicketAssignIn) -> dict:
    _require_feature(db)
    user.require_perm("ticket:assign")
    ticket = _get(db, ticket_id)
    # 'create' -> 'assign' and reassign ('assign' -> 'assign', self-loop allowed).
    _apply_transition(ticket, "assign")
    ticket.assignee_id = data.assignee_id
    db.commit()
    return _out(ticket)


def accept_ticket(db: Session, user, ticket_id: int) -> dict:
    return _simple_transition(db, user, ticket_id, "accept", "ticket:accept")


def process_ticket(db: Session, user, ticket_id: int) -> dict:
    return _simple_transition(db, user, ticket_id, "process", "ticket:process")


def close_ticket(db: Session, user, ticket_id: int) -> dict:
    return _simple_transition(db, user, ticket_id, "close", "ticket:close")


def reopen_ticket(db: Session, user, ticket_id: int) -> dict:
    return _simple_transition(db, user, ticket_id, "reopen", "ticket:reopen")


def cancel_ticket(db: Session, user, ticket_id: int) -> dict:
    return _simple_transition(db, user, ticket_id, "cancel", "ticket:cancel")


def _simple_transition(db: Session, user, ticket_id: int, action: str, perm: str) -> dict:
    _require_feature(db)
    user.require_perm(perm)
    ticket = _get(db, ticket_id)
    _apply_transition(ticket, action)
    if action == "close":
        ticket.closed_at = datetime.now(timezone.utc)
    db.commit()
    return _out(ticket)


def done_ticket(db: Session, user, ticket_id: int, data: schemas.TicketDoneIn | None = None) -> dict:
    _require_feature(db)
    user.require_perm("ticket:done")
    ticket = _get(db, ticket_id)
    _apply_transition(ticket, "done")
    ticket.resolved_at = datetime.now(timezone.utc)
    if data is not None and data.exec_task_id:
        db.add(TicketRef(ticket_id=ticket.id, ref_type="exec_task", ref_id=data.exec_task_id,
                         created_by=user.id))
    db.commit()
    return _out(ticket)


# =============================================================== comments/attachments/refs


def add_comment(db: Session, user, ticket_id: int, data: schemas.TicketCommentIn) -> dict:
    _require_feature(db)
    user.require_perm("ticket:comment")
    ticket = _get(db, ticket_id)
    comment = TicketComment(ticket_id=ticket.id, author_id=user.id, content=data.content)
    db.add(comment)
    db.commit()
    return {
        "id": comment.id,
        "ticket_id": ticket.id,
        "author_id": user.id,
        "content": comment.content,
        "created_at": _iso(comment.created_at),
    }


def add_attachments(db: Session, user, ticket_id: int, files: list) -> dict:
    _require_feature(db)
    user.require_perm("ticket:attachment")
    ticket = _get(db, ticket_id)
    if not files:
        raise BadRequestError("files[] required")

    store_root = Path(settings.transfer_store_dir) / "tickets" / str(ticket.id)
    store_root.mkdir(parents=True, exist_ok=True)
    created = []
    for f in files:
        name = (getattr(f, "filename", "") or getattr(f, "name", "") or "file").split("/")[-1]
        data = f.file.read() if hasattr(f, "file") else (f.read() if hasattr(f, "read") else b"")
        dest = store_root / name
        dest.write_bytes(data)
        pkg = FilePackage(
            name=name,
            file_count=1,
            total_size=len(data),
            store_path=str(dest),
            created_by=user.id,
        )
        db.add(pkg)
        db.flush()
        attachment = TicketAttachment(
            ticket_id=ticket.id,
            file_id=pkg.id,
            filename=name,
            size=len(data),
            uploaded_by=user.id,
        )
        db.add(attachment)
        db.flush()
        created.append({"id": attachment.id, "file_id": pkg.id, "filename": name,
                        "size": len(data)})
    db.commit()
    return {"ticket_id": ticket.id, "attachments": created}


def add_ref(db: Session, user, ticket_id: int, data: schemas.TicketRefIn) -> dict:
    """Idempotent: duplicate (ticket_id, ref_type, ref_id) returns the existing row."""
    _require_feature(db)
    user.require_perm("ticket:ref")
    ticket = _get(db, ticket_id)
    if data.ref_type not in TICKET_REF_TYPES:
        raise ValidationError(f"invalid ref_type: {data.ref_type}")
    existing = db.scalar(
        select(TicketRef).where(
            TicketRef.ticket_id == ticket.id,
            TicketRef.ref_type == data.ref_type,
            TicketRef.ref_id == data.ref_id,
        )
    )
    if existing is not None:
        return {"id": existing.id, "ticket_id": ticket.id, "ref_type": existing.ref_type,
                "ref_id": existing.ref_id, "created": False}
    ref = TicketRef(ticket_id=ticket.id, ref_type=data.ref_type, ref_id=data.ref_id,
                    created_by=user.id)
    db.add(ref)
    db.commit()
    return {"id": ref.id, "ticket_id": ticket.id, "ref_type": ref.ref_type,
            "ref_id": ref.ref_id, "created": True}
