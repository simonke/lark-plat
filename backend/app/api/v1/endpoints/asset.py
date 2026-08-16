"""Asset endpoints: hosts CRUD/import/export/conn/stats, groups tree, credentials, options."""

from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import asset as sch
from app.services import asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/hosts", response_model=Result)
def list_hosts(
    db: DbDep,
    user: UserDep,
    hostname: str | None = None,
    ip: str | None = None,
    os_type: str | None = None,
    group_id: int | None = None,
    env: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    connector: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    user.require_perm("asset:host:list")
    return Result.ok(asset_service.list_hosts(db, user, hostname, ip, os_type, group_id, env, tag, status, connector, page, size))


@router.post("/hosts/import", response_model=Result)
async def import_hosts(db: DbDep, user: UserDep, file: UploadFile = File(...)):
    user.require_perm("asset:host:import")
    content = await file.read()
    return Result.ok(asset_service.import_hosts(db, user, content))


@router.get("/hosts/export")
def export_hosts(db: DbDep, user: UserDep):
    user.require_perm("asset:host:export")
    data = asset_service.export_hosts(db, user)
    return Response(content=data, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=hosts.csv"})


@router.get("/hosts/stats", response_model=Result)
def host_stats(db: DbDep, user: UserDep):
    user.require_perm("asset:host:list")
    return Result.ok(asset_service.host_stats(db, user))


@router.get("/hosts/{host_id}", response_model=Result)
def get_host(db: DbDep, user: UserDep, host_id: int):
    user.require_perm("asset:host:list")
    return Result.ok(asset_service.get_host(db, user, host_id))


@router.post("/hosts", response_model=Result)
def create_host(db: DbDep, user: UserDep, data: sch.HostCreate):
    user.require_perm("asset:host:add")
    return Result.ok({"id": asset_service.create_host(db, user, data)})


@router.put("/hosts/{host_id}", response_model=Result)
def update_host(db: DbDep, user: UserDep, host_id: int, data: sch.HostUpdate):
    user.require_perm("asset:host:edit")
    asset_service.update_host(db, user, host_id, data)
    return Result.ok()


@router.delete("/hosts/{host_id}", response_model=Result)
def delete_host(db: DbDep, user: UserDep, host_id: int):
    user.require_perm("asset:host:del")
    asset_service.delete_host(db, user, host_id)
    return Result.ok()


@router.post("/hosts/{host_id}/conn", response_model=Result)
def connectivity(db: DbDep, user: UserDep, host_id: int):
    user.require_perm("asset:host:conn")
    return Result.ok(asset_service.connectivity_check(db, user, host_id))


@router.get("/groups/tree", response_model=Result)
def group_tree(db: DbDep, user: UserDep):
    user.require_perm("asset:group:list")
    return Result.ok(asset_service.group_tree(db, user))


@router.post("/groups", response_model=Result)
def create_group(db: DbDep, user: UserDep, data: sch.GroupCreate):
    user.require_perm("asset:group:add")
    return Result.ok({"id": asset_service.create_group(db, data)})


@router.put("/groups/{group_id}", response_model=Result)
def update_group(db: DbDep, user: UserDep, group_id: int, data: sch.GroupUpdate):
    user.require_perm("asset:group:edit")
    asset_service.update_group(db, group_id, data)
    return Result.ok()


@router.delete("/groups/{group_id}", response_model=Result)
def delete_group(db: DbDep, user: UserDep, group_id: int):
    user.require_perm("asset:group:del")
    asset_service.delete_group(db, group_id)
    return Result.ok()


@router.get("/credentials", response_model=Result)
def list_credentials(db: DbDep, user: UserDep):
    user.require_perm("asset:cred:list")
    return Result.ok(asset_service.list_credentials(db, user))


@router.post("/credentials", response_model=Result)
def create_credential(db: DbDep, user: UserDep, data: sch.CredentialCreate):
    user.require_perm("asset:cred:add")
    return Result.ok({"id": asset_service.create_credential(db, user, data)})


@router.put("/credentials/{cred_id}", response_model=Result)
def update_credential(db: DbDep, user: UserDep, cred_id: int, data: sch.CredentialUpdate):
    user.require_perm("asset:cred:edit")
    asset_service.update_credential(db, user, cred_id, data)
    return Result.ok()


@router.delete("/credentials/{cred_id}", response_model=Result)
def delete_credential(db: DbDep, user: UserDep, cred_id: int):
    user.require_perm("asset:cred:del")
    asset_service.delete_credential(db, user, cred_id)
    return Result.ok()


@router.get("/options", response_model=Result)
def options(db: DbDep, user: UserDep):
    return Result.ok(asset_service.options(db, user))
