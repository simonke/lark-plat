"""Exec endpoints: task CRUD, stop/retry, stats, log pagination (after_seq replay)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import exec_service

router = APIRouter(prefix="/exec", tags=["exec"])


@router.get("/tasks", response_model=Result)
def list_tasks(
    db: DbDep,
    user: UserDep,
    task_no: str | None = None,
    name: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(exec_service.list_tasks(db, user, task_no, name, status, kind, start, end, page, size))


@router.post("/tasks", response_model=Result)
def create_task(db: DbDep, user: UserDep, data: schemas.ExecTaskCreate):
    return Result.ok(exec_service.create_task(db, user, data))


@router.get("/tasks/{task_id}", response_model=Result)
def get_task(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(exec_service.get_task(db, user, task_id))


@router.get("/tasks/{task_id}/stats", response_model=Result)
def task_stats(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(exec_service.task_stats(db, user, task_id))


@router.post("/tasks/{task_id}/stop", response_model=Result)
def stop_task(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(exec_service.stop_task(db, user, task_id))


@router.post("/tasks/{task_id}/retry", response_model=Result)
def retry_task(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(exec_service.retry_task(db, user, task_id))


@router.get("/tasks/{task_id}/hosts/{task_host_id}/logs", response_model=Result)
def task_logs(
    db: DbDep,
    user: UserDep,
    task_id: int,
    task_host_id: int,
    after_seq: int = 0,
    size: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    return Result.ok(exec_service.get_logs(db, user, task_id, task_host_id, after_seq, size))


@router.get("/tasks/{task_id}/hosts/{task_host_id}/ws-token", response_model=Result)
def task_ws_token(db: DbDep, user: UserDep, task_id: int, task_host_id: int):
    return Result.ok(exec_service.ws_token(db, user, task_id, task_host_id))
