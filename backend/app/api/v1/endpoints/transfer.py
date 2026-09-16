"""Transfer endpoints: packages (multipart), tasks (run/stop/retry/stats/logs/mine).

Mirrors api-design-v3 §transfer: 13 endpoints. Static segments register before
`{id}` param segments. Feature-flag/whitelist/perm guards live in the service.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import transfer_service

router = APIRouter(prefix="/transfer", tags=["transfer"])


# ---------------------------------------------------------------- packages
@router.post("/packages", response_model=Result)
def create_package(
    db: DbDep,
    user: UserDep,
    files: Annotated[list[UploadFile], File(description="files to package")],
    name: Annotated[str | None, Form()] = None,
):
    return Result.ok(transfer_service.create_package(db, user, files, name or ""))


@router.get("/packages", response_model=Result)
def list_packages(
    db: DbDep,
    user: UserDep,
    name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(transfer_service.list_packages(db, user, name, start, end, page, size))


@router.get("/packages/{package_id}", response_model=Result)
def get_package(db: DbDep, user: UserDep, package_id: int):
    return Result.ok(transfer_service.get_package(db, user, package_id))


@router.delete("/packages/{package_id}", response_model=Result)
def delete_package(db: DbDep, user: UserDep, package_id: int):
    return Result.ok(transfer_service.delete_package(db, user, package_id))


# ---------------------------------------------------------------- tasks
@router.post("/tasks", response_model=Result)
def create_task(db: DbDep, user: UserDep, data: schemas.TransferTaskCreate):
    return Result.ok(transfer_service.create_task(db, user, data))


@router.get("/tasks", response_model=Result)
def list_tasks(
    db: DbDep,
    user: UserDep,
    mode: str | None = None,
    status: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(transfer_service.list_tasks(db, user, mode, status, start, end, page, size))


@router.get("/tasks/mine", response_model=Result)
def list_my_tasks(
    db: DbDep,
    user: UserDep,
    mode: str | None = None,
    status: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(transfer_service.list_my_tasks(db, user, mode, status, start, end, page, size))


@router.get("/tasks/{task_id}", response_model=Result)
def get_task(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(transfer_service.get_task(db, user, task_id))


@router.get("/tasks/{task_id}/stats", response_model=Result)
def task_stats(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(transfer_service.task_stats(db, user, task_id))


@router.post("/tasks/{task_id}/stop", response_model=Result)
def stop_task(db: DbDep, user: UserDep, task_id: int):
    return Result.ok(transfer_service.stop_task(db, user, task_id))


@router.post("/tasks/{task_id}/hosts/{transfer_host_id}/retry", response_model=Result)
def retry_host(db: DbDep, user: UserDep, task_id: int, transfer_host_id: int):
    return Result.ok(transfer_service.retry_host(db, user, task_id, transfer_host_id))


@router.get("/tasks/{task_id}/hosts/{transfer_host_id}/logs", response_model=Result)
def task_logs(
    db: DbDep,
    user: UserDep,
    task_id: int,
    transfer_host_id: int,
    after_seq: int = 0,
    size: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    return Result.ok(transfer_service.get_logs(db, user, task_id, transfer_host_id, after_seq, size))


@router.get("/tasks/{task_id}/hosts/{transfer_host_id}/ws-token", response_model=Result)
def ws_token(db: DbDep, user: UserDep, task_id: int, transfer_host_id: int):
    return Result.ok(transfer_service.ws_token(db, user, task_id, transfer_host_id))