"""Web Terminal endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import terminal_service

router = APIRouter(prefix="/terminals", tags=["terminals"])


@router.get("", response_model=Result)
def list_terminals(
    db: DbDep,
    user: UserDep,
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(terminal_service.list_sessions(db, user, status, page, size))


@router.post("", response_model=Result)
def create_terminal(db: DbDep, user: UserDep, data: schemas.TerminalCreate):
    return Result.ok(terminal_service.create_session(db, user, data))


@router.get("/{session_id}", response_model=Result)
def get_terminal(db: DbDep, user: UserDep, session_id: int):
    return Result.ok(terminal_service.get_session(db, user, session_id))


@router.post("/{session_id}/token", response_model=Result)
def get_token(db: DbDep, user: UserDep, session_id: int):
    return Result.ok(terminal_service.issue_token(db, user, session_id))


@router.post("/{session_id}/close", response_model=Result)
def close_terminal(db: DbDep, user: UserDep, session_id: int):
    return Result.ok(terminal_service.close_session(db, user, session_id))


@router.get("/{session_id}/recording", response_model=Result)
def get_recording(
    db: DbDep,
    user: UserDep,
    session_id: int,
    after_offset: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=200)] = 100,
):
    return Result.ok(
        terminal_service.replay_recording(db, user, session_id, after_offset, size)
    )
