"""P6 (AIOps E6) endpoints: governed automation level / whitelist / dry-run /
rollback / circuit-breaker.

Routes are ALWAYS registered ((A) unconditional) so the committed/served openapi
surface is 173 keys regardless of the flag; feature/permission gates live in the
service (feature-first), so with the flag off a caller gets 400/403, never 404.

Frozen contract: @架构 P6 tuple r1 (seq3560 + notes r1.1-r1.7) + @需求 §30.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.services import ai_automation_service as svc

router = APIRouter(prefix="/ai/automation", tags=["ai-automation"])


class LevelIn(BaseModel):
    current: str = Field(min_length=1, max_length=16)


class WhitelistIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    risk_level: str = Field(min_length=1, max_length=16)
    enabled: bool = True


class WhitelistUpdateIn(BaseModel):
    risk_level: str | None = Field(default=None, max_length=16)
    enabled: bool | None = None


class DryRunIn(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    action: str | None = Field(default=None, max_length=64)
    target: str | None = Field(default=None, max_length=256)


@router.get("/level", response_model=Result)
def get_level(db: DbDep, user: UserDep):
    return Result.ok(svc.get_level(db, user))


@router.put("/level", response_model=Result)
def put_level(db: DbDep, user: UserDep, data: LevelIn):
    return Result.ok(svc.put_level(db, user, data.current))


@router.get("/whitelist", response_model=Result)
def list_whitelist(
    db: DbDep,
    user: UserDep,
    action: str | None = None,
    enabled: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(svc.list_whitelist(db, user, page, size, action, enabled))


@router.post("/whitelist", response_model=Result)
def create_whitelist(db: DbDep, user: UserDep, data: WhitelistIn):
    return Result.ok(svc.create_whitelist(db, user, data.action, data.risk_level, data.enabled))


@router.put("/whitelist/{item_id}", response_model=Result)
def update_whitelist(db: DbDep, user: UserDep, item_id: int, data: WhitelistUpdateIn):
    return Result.ok(svc.update_whitelist(db, user, item_id, data.risk_level, data.enabled))


@router.delete("/whitelist/{item_id}", response_model=Result)
def delete_whitelist(db: DbDep, user: UserDep, item_id: int):
    return Result.ok(svc.delete_whitelist(db, user, item_id))


@router.post("/dry-run", response_model=Result)
def dry_run(db: DbDep, user: UserDep, data: DryRunIn):
    return Result.ok(svc.dry_run(db, user, data))


@router.post("/runs/{run_id}/rollback", response_model=Result)
def rollback_run(db: DbDep, user: UserDep, run_id: int):
    return Result.ok(svc.rollback_run(db, user, run_id))


@router.get("/circuit-breaker", response_model=Result)
def circuit_breaker(db: DbDep, user: UserDep):
    return Result.ok(svc.circuit_breaker(db, user))
