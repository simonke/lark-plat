"""Asset endpoints: hosts CRUD/import/export/conn/stats, groups tree, credentials, options."""

from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import asset as sch
from app.services import asset_service, cmdb_service

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


# P2-SS: asset:host:executor reuses the asset:host:edit enforcement surface
# (api-design-v3 §4), so the check stays on the existing permission code.
@router.get("/hosts/{host_id}/executors", response_model=Result)
def host_executors(db: DbDep, user: UserDep, host_id: int):
    user.require_perm("asset:host:edit")
    return Result.ok(asset_service.host_executors(db, user, host_id))


@router.put("/hosts/{host_id}/connector", response_model=Result)
def update_connector(db: DbDep, user: UserDep, host_id: int, data: sch.ConnectorUpdate):
    user.require_perm("asset:host:edit")
    asset_service.update_connector(db, user, host_id, data)
    return Result.ok()


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


# ------------------------------------------------------------------ P3-3 CMDB


@router.get("/relations", response_model=Result)
def list_relations(
    db: DbDep,
    user: UserDep,
    src_type: str | None = None,
    src_id: int | None = None,
    dst_type: str | None = None,
    dst_id: int | None = None,
    rel_type: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    user.require_perm("asset:relation:list")
    return Result.ok(cmdb_service.list_relations(
        db, user,
        {"src_type": src_type, "src_id": src_id, "dst_type": dst_type,
         "dst_id": dst_id, "rel_type": rel_type},
        page, size,
    ))


@router.post("/relations", response_model=Result)
def create_relation(db: DbDep, user: UserDep, data: sch.RelationCreate):
    user.require_perm("asset:relation:add")
    return Result.ok(cmdb_service.create_relation(db, user, data))


@router.delete("/relations/{relation_id}", response_model=Result)
def delete_relation(db: DbDep, user: UserDep, relation_id: int):
    user.require_perm("asset:relation:del")
    cmdb_service.delete_relation(db, user, relation_id)
    return Result.ok()


@router.get("/cmdb/topology", response_model=Result)
def cmdb_topology(
    db: DbDep,
    user: UserDep,
    entity_type: str,
    entity_id: int,
    direction: str = "both",
    depth: int = 2,
    rel_types: Annotated[list[str] | None, Query()] = None,
):
    user.require_perm("asset:topo:view")
    return Result.ok(cmdb_service.topology(
        db, user, entity_type, entity_id, direction, depth, rel_types
    ))


@router.get("/cmdb/impact", response_model=Result)
def cmdb_impact(
    db: DbDep,
    user: UserDep,
    entity_type: str,
    entity_id: int,
    direction: str = "down",
    depth: int = 2,
    rel_types: Annotated[list[str] | None, Query()] = None,
):
    user.require_perm("asset:topo:view")
    return Result.ok(cmdb_service.impact(
        db, user, entity_type, entity_id, direction, depth, rel_types
    ))
