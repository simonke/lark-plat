"""Notify endpoints: channels CRUD/test, records/resend."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import notify_service

router = APIRouter(prefix="/notify", tags=["notify"])


@router.get("/channels", response_model=Result)
def list_channels(db: DbDep, user: UserDep):
    user.require_perm("notify:channel:list")
    return Result.ok(notify_service.list_channels(db))


@router.post("/channels", response_model=Result)
def create_channel(db: DbDep, user: UserDep, data: schemas.ChannelCreate):
    user.require_perm("notify:channel:add")
    return Result.ok({"id": notify_service.create_channel(db, data)})


@router.put("/channels/{channel_id}", response_model=Result)
def update_channel(db: DbDep, user: UserDep, channel_id: int, data: schemas.ChannelUpdate):
    user.require_perm("notify:channel:edit")
    notify_service.update_channel(db, channel_id, data)
    return Result.ok()


@router.delete("/channels/{channel_id}", response_model=Result)
def delete_channel(db: DbDep, user: UserDep, channel_id: int):
    user.require_perm("notify:channel:del")
    notify_service.delete_channel(db, channel_id)
    return Result.ok()


@router.put("/channels/{channel_id}/status", response_model=Result)
def set_status(db: DbDep, user: UserDep, channel_id: int, data: schemas.ScheduleStatusIn):
    user.require_perm("notify:channel:edit")
    notify_service.set_channel_status(db, channel_id, data.enabled)
    return Result.ok()


@router.post("/channels/{channel_id}/test", response_model=Result)
def test_channel(db: DbDep, user: UserDep, channel_id: int, data: schemas.ChannelTestIn):
    user.require_perm("notify:channel:test")
    return Result.ok(notify_service.test_send(db, channel_id, data.title, data.content))


@router.get("/records", response_model=Result)
def list_records(db: DbDep, user: UserDep, channel_id: int | None = None, scene: str | None = None,
                 status: str | None = None, start: str | None = None, end: str | None = None,
                 page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10):
    user.require_perm("notify:record:list")
    return Result.ok(notify_service.list_records(db, channel_id, scene, status, start, end, page, size))


@router.post("/records/{record_id}/resend", response_model=Result)
def resend(db: DbDep, user: UserDep, record_id: int):
    user.require_perm("notify:record:list")
    return Result.ok(notify_service.resend(db, record_id))
