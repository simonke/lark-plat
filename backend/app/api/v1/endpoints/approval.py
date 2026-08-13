"""Approval endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Result)
def list_approvals(
    db: DbDep,
    user: UserDep,
    status: str | None = None,
    biz_type: str | None = None,
    mine: bool = False,
    todo: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    user.require_perm("approval:list")
    return Result.ok(approval_service.list_approvals(db, user, status, biz_type, mine, todo, page, size))


@router.get("/rules", response_model=Result)
def list_rules(db: DbDep, user: UserDep):
    user.require_perm("approval:list")
    return Result.ok(approval_service.list_rules(db))


@router.post("/rules", response_model=Result)
def create_rule(db: DbDep, user: UserDep, data: schemas.RuleCreate):
    user.require_perm("approval:approve")
    return Result.ok({"id": approval_service.create_rule(db, data)})


@router.put("/rules/{rule_id}", response_model=Result)
def update_rule(db: DbDep, user: UserDep, rule_id: int, data: schemas.RuleUpdate):
    user.require_perm("approval:approve")
    approval_service.update_rule(db, rule_id, data)
    return Result.ok()


@router.delete("/rules/{rule_id}", response_model=Result)
def delete_rule(db: DbDep, user: UserDep, rule_id: int):
    user.require_perm("approval:approve")
    approval_service.delete_rule(db, rule_id)
    return Result.ok()


@router.get("/{approval_id}", response_model=Result)
def detail(db: DbDep, user: UserDep, approval_id: int):
    user.require_perm("approval:list")
    return Result.ok(approval_service.detail(db, approval_id))


@router.post("/{approval_id}/approve", response_model=Result)
def approve(db: DbDep, user: UserDep, approval_id: int, data: schemas.ApproveIn):
    return Result.ok(approval_service.approve(db, user, approval_id, data.comment))


@router.post("/{approval_id}/reject", response_model=Result)
def reject(db: DbDep, user: UserDep, approval_id: int, data: schemas.ApproveIn):
    return Result.ok(approval_service.reject(db, user, approval_id, data.comment))


@router.post("/{approval_id}/cancel", response_model=Result)
def cancel(db: DbDep, user: UserDep, approval_id: int):
    return Result.ok(approval_service.cancel(db, user, approval_id))
