"""Script library endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import script_service

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.get("", response_model=Result)
def list_scripts(db: DbDep, user: UserDep, name: str | None = None, type: str | None = None,
                 page: Annotated[int, Query(ge=1)] = 1, size: Annotated[int, Query(ge=1, le=100)] = 10):
    user.require_perm("script:list")
    return Result.ok(script_service.list_scripts(db, name, type, page, size))


@router.post("", response_model=Result)
def create_script(db: DbDep, user: UserDep, data: schemas.ScriptCreate):
    user.require_perm("script:add")
    return Result.ok({"id": script_service.create_script(db, user, data)})


@router.get("/{script_id}", response_model=Result)
def get_script(db: DbDep, user: UserDep, script_id: int, version: int | None = None):
    user.require_perm("script:list")
    return Result.ok(script_service.get_script(db, script_id, version))


@router.put("/{script_id}", response_model=Result)
def update_script(db: DbDep, user: UserDep, script_id: int, data: schemas.ScriptUpdate):
    user.require_perm("script:edit")
    return Result.ok(script_service.update_script(db, user, script_id, data))


@router.delete("/{script_id}", response_model=Result)
def delete_script(db: DbDep, user: UserDep, script_id: int):
    user.require_perm("script:del")
    script_service.delete_script(db, script_id)
    return Result.ok()


@router.get("/{script_id}/versions", response_model=Result)
def list_versions(db: DbDep, user: UserDep, script_id: int):
    user.require_perm("script:version")
    return Result.ok(script_service.list_versions(db, script_id))


@router.get("/{script_id}/versions/{version}", response_model=Result)
def get_version(db: DbDep, user: UserDep, script_id: int, version: int):
    user.require_perm("script:version")
    return Result.ok(script_service.get_version(db, script_id, version))


@router.post("/{script_id}/rollback", response_model=Result)
def rollback(db: DbDep, user: UserDep, script_id: int, data: schemas.RollbackIn):
    user.require_perm("script:rollback")
    return Result.ok(script_service.rollback(db, user, script_id, data.version))


@router.post("/{script_id}/test", response_model=Result)
def test_script(db: DbDep, user: UserDep, script_id: int, data: schemas.ScriptTestIn):
    user.require_perm("script:list")
    return Result.ok(script_service.test_params(db, script_id, data.params))
