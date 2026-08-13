"""Schedule (cron) endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import schedule_service

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("", response_model=Result)
def list_schedules(db: DbDep, user: UserDep, name: str | None = None, enabled: int | None = None,
                   page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10):
    user.require_perm("schedule:list")
    return Result.ok(schedule_service.list_schedules(db, name, enabled, page, size))


@router.post("", response_model=Result)
def create_schedule(db: DbDep, user: UserDep, data: schemas.ScheduleCreate):
    user.require_perm("schedule:add")
    return Result.ok({"id": schedule_service.create_schedule(db, user, data)})


@router.put("/{schedule_id}", response_model=Result)
def update_schedule(db: DbDep, user: UserDep, schedule_id: int, data: schemas.ScheduleUpdate):
    user.require_perm("schedule:edit")
    schedule_service.update_schedule(db, schedule_id, data)
    return Result.ok()


@router.delete("/{schedule_id}", response_model=Result)
def delete_schedule(db: DbDep, user: UserDep, schedule_id: int):
    user.require_perm("schedule:del")
    schedule_service.delete_schedule(db, schedule_id)
    return Result.ok()


@router.put("/{schedule_id}/status", response_model=Result)
def set_status(db: DbDep, user: UserDep, schedule_id: int, data: schemas.ScheduleStatusIn):
    user.require_perm("schedule:edit")
    schedule_service.set_schedule_status(db, schedule_id, data.enabled)
    return Result.ok()


@router.post("/{schedule_id}/run-now", response_model=Result)
def run_now(db: DbDep, user: UserDep, schedule_id: int):
    user.require_perm("schedule:run")
    return Result.ok(schedule_service.run_now(db, schedule_id))


@router.get("/{schedule_id}/runs", response_model=Result)
def list_runs(db: DbDep, user: UserDep, schedule_id: int,
              page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10):
    user.require_perm("schedule:list")
    return Result.ok(schedule_service.list_runs(db, schedule_id, page, size))


@router.post("/{schedule_id}/runs/{run_id}/retry", response_model=Result)
def retry_run(db: DbDep, user: UserDep, schedule_id: int, run_id: int):
    user.require_perm("schedule:retry")
    return Result.ok(schedule_service.retry_run(db, schedule_id, run_id))
