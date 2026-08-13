"""System management endpoints: users, roles, permissions, audit logs."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import system as sch
from app.services import system_service

router = APIRouter(prefix="/system", tags=["system"])


# ---------------------------------------------------------------- users


@router.get("/users", response_model=Result)
def list_users(
    db: DbDep,
    user: UserDep,
    username: str | None = None,
    real_name: str | None = None,
    status: int | None = None,
    role_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    user.require_perm("system:user:list")
    return Result.ok(system_service.list_users(db, username, real_name, status, role_id, page, size))


@router.post("/users", response_model=Result)
def create_user(db: DbDep, user: UserDep, data: sch.UserCreate):
    user.require_perm("system:user:add")
    return Result.ok({"id": system_service.create_user(db, data)})


@router.put("/users/{user_id}", response_model=Result)
def update_user(db: DbDep, user: UserDep, user_id: int, data: sch.UserUpdate):
    user.require_perm("system:user:edit")
    system_service.update_user(db, user_id, data)
    return Result.ok()


@router.delete("/users/{user_id}", response_model=Result)
def delete_user(db: DbDep, user: UserDep, user_id: int):
    user.require_perm("system:user:del")
    system_service.delete_user(db, user_id, user.id)
    return Result.ok()


@router.put("/users/{user_id}/roles", response_model=Result)
def set_user_roles(db: DbDep, user: UserDep, user_id: int, data: sch.UserRolesIn):
    user.require_perm("system:user:role")
    system_service.set_user_roles(db, user_id, data.role_ids)
    return Result.ok()


@router.put("/users/{user_id}/status", response_model=Result)
def set_user_status(db: DbDep, user: UserDep, user_id: int, data: sch.UserStatusIn):
    user.require_perm("system:user:edit")
    system_service.set_user_status(db, user_id, data.status)
    return Result.ok()


@router.put("/users/{user_id}/password", response_model=Result)
def reset_password(db: DbDep, user: UserDep, user_id: int, data: sch.ResetPasswordIn):
    user.require_perm("system:user:edit")
    system_service.reset_password(db, user_id, data.password)
    return Result.ok()


# ---------------------------------------------------------------- roles


@router.get("/roles", response_model=Result)
def list_roles(db: DbDep, user: UserDep):
    user.require_perm("system:role:list")
    return Result.ok(system_service.list_roles(db))


@router.post("/roles", response_model=Result)
def create_role(db: DbDep, user: UserDep, data: sch.RoleCreate):
    user.require_perm("system:role:add")
    return Result.ok({"id": system_service.create_role(db, data)})


@router.put("/roles/{role_id}", response_model=Result)
def update_role(db: DbDep, user: UserDep, role_id: int, data: sch.RoleUpdate):
    user.require_perm("system:role:edit")
    system_service.update_role(db, role_id, data)
    return Result.ok()


@router.delete("/roles/{role_id}", response_model=Result)
def delete_role(db: DbDep, user: UserDep, role_id: int):
    user.require_perm("system:role:del")
    system_service.delete_role(db, role_id)
    return Result.ok()


@router.put("/roles/{role_id}/permissions", response_model=Result)
def set_role_permissions(db: DbDep, user: UserDep, role_id: int, data: sch.RoleIdsIn):
    user.require_perm("system:role:perm")
    system_service.set_role_permissions(db, role_id, data.permission_ids)
    return Result.ok()


@router.put("/roles/{role_id}/groups", response_model=Result)
def set_role_groups(db: DbDep, user: UserDep, role_id: int, data: sch.GroupIdsIn):
    """Data permission: visible host groups for a role (US-03)."""
    user.require_perm("system:role:group")
    system_service.set_role_groups(db, role_id, data.group_ids)
    return Result.ok()


# ---------------------------------------------------------------- permissions


@router.get("/permissions", response_model=Result)
def permission_tree(db: DbDep, user: UserDep):
    user.require_perm("system:permission:list")
    return Result.ok(system_service.permission_tree(db))


# ---------------------------------------------------------------- audit


@router.get("/audit-logs", response_model=Result)
def list_audit_logs(
    db: DbDep,
    user: UserDep,
    module: str | None = None,
    action: str | None = None,
    username: str | None = None,
    ip: str | None = None,
    start: str | None = None,
    end: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    user.require_perm("system:audit:list")
    return Result.ok(system_service.list_audit_logs(db, module, action, username, ip, start, end, page, size))


@router.get("/audit-logs/export")
def export_audit_logs(
    db: DbDep,
    user: UserDep,
    module: str | None = None,
    username: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    user.require_perm("system:audit:export")
    result = system_service.list_audit_logs(db, module, None, username, None, start, end, 1, 100000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "username", "module", "action", "method", "path", "ip", "status", "cost_ms", "trace_id", "created_at"])
    for row in result["list"]:
        writer.writerow([row["id"], row["username"], row["module"], row["action"], row["method"],
                         row["path"], row["ip"], row["status"], row["cost_ms"], row["trace_id"],
                         row["created_at"]])
    from fastapi.responses import Response

    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=audit-logs.csv"})


@router.get("/audit-logs/{log_id}", response_model=Result)
def audit_log_detail(db: DbDep, user: UserDep, log_id: int):
    user.require_perm("system:audit:list")
    return Result.ok(system_service.audit_log_detail(db, log_id))
