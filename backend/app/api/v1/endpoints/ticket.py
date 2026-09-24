"""Ticket endpoints (P3-1): CRUD + lifecycle transitions + comments/attachments/refs.

Static segments register before `{id}` param segments. The feature flag/permission
guards live in the service (routes stay registered so openapi keeps every key).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=Result)
def list_tickets(
    db: DbDep,
    user: UserDep,
    category: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    requester_id: int | None = None,
    assignee_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    filters = {
        "category": category, "status": status, "priority": priority,
        "requester_id": requester_id, "assignee_id": assignee_id,
        "start": start, "end": end,
    }
    return Result.ok(ticket_service.list_tickets(db, user, filters, page, size))


@router.post("", response_model=Result)
def create_ticket(db: DbDep, user: UserDep, data: schemas.TicketCreate):
    return Result.ok(ticket_service.create_ticket(db, user, data))


@router.get("/{ticket_id}", response_model=Result)
def get_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.get_ticket(db, user, ticket_id))


@router.put("/{ticket_id}", response_model=Result)
def edit_ticket(db: DbDep, user: UserDep, ticket_id: int, data: schemas.TicketUpdate):
    return Result.ok(ticket_service.edit_ticket(db, user, ticket_id, data))


@router.post("/{ticket_id}/assign", response_model=Result)
def assign_ticket(db: DbDep, user: UserDep, ticket_id: int, data: schemas.TicketAssignIn):
    return Result.ok(ticket_service.assign_ticket(db, user, ticket_id, data))


@router.post("/{ticket_id}/accept", response_model=Result)
def accept_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.accept_ticket(db, user, ticket_id))


@router.post("/{ticket_id}/process", response_model=Result)
def process_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.process_ticket(db, user, ticket_id))


@router.post("/{ticket_id}/done", response_model=Result)
def done_ticket(db: DbDep, user: UserDep, ticket_id: int, data: schemas.TicketDoneIn | None = None):
    return Result.ok(ticket_service.done_ticket(db, user, ticket_id, data))


@router.post("/{ticket_id}/close", response_model=Result)
def close_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.close_ticket(db, user, ticket_id))


@router.post("/{ticket_id}/reopen", response_model=Result)
def reopen_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.reopen_ticket(db, user, ticket_id))


@router.post("/{ticket_id}/cancel", response_model=Result)
def cancel_ticket(db: DbDep, user: UserDep, ticket_id: int):
    return Result.ok(ticket_service.cancel_ticket(db, user, ticket_id))


@router.post("/{ticket_id}/comments", response_model=Result)
def add_comment(db: DbDep, user: UserDep, ticket_id: int, data: schemas.TicketCommentIn):
    return Result.ok(ticket_service.add_comment(db, user, ticket_id, data))


@router.post("/{ticket_id}/attachments", response_model=Result)
def add_attachments(
    db: DbDep,
    user: UserDep,
    ticket_id: int,
    files: Annotated[list[UploadFile], File(description="attachments")],
):
    return Result.ok(ticket_service.add_attachments(db, user, ticket_id, files))


@router.post("/{ticket_id}/refs", response_model=Result)
def add_ref(db: DbDep, user: UserDep, ticket_id: int, data: schemas.TicketRefIn):
    return Result.ok(ticket_service.add_ref(db, user, ticket_id, data))
