"""CI/CD integration endpoints (P3-5): providers + release orchestration.

Static segments register before `{id}` segments. Feature-flag/permission guards
live in the service (routes stay registered so openapi keeps every key, and the
feature gate runs FIRST for any caller). The inbound webhook is **provider-token
gated, NOT session** — it deliberately does not depend on `UserDep`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import cicd as sch
from app.services import cicd_service

router = APIRouter(prefix="/cicd", tags=["cicd"])
release_router = APIRouter(prefix="/releases", tags=["releases"])


# ---------------------------------------------------------------- providers


@router.get("/providers", response_model=Result)
def list_providers(
    db: DbDep,
    user: UserDep,
    name: str | None = None,
    type: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(cicd_service.list_providers(
        db, user, {"name": name, "type": type}, page, size
    ))


@router.post("/providers", response_model=Result)
def create_provider(db: DbDep, user: UserDep, data: sch.ProviderCreate):
    return Result.ok(cicd_service.create_provider(db, user, data))


@router.put("/providers/{provider_id}", response_model=Result)
def update_provider(
    db: DbDep, user: UserDep, provider_id: int, data: sch.ProviderUpdate
):
    return Result.ok(cicd_service.update_provider(db, user, provider_id, data))


@router.delete("/providers/{provider_id}", response_model=Result)
def delete_provider(db: DbDep, user: UserDep, provider_id: int):
    cicd_service.delete_provider(db, user, provider_id)
    return Result.ok()


@router.post("/providers/{provider_id}/test", response_model=Result)
def test_provider(db: DbDep, user: UserDep, provider_id: int):
    return Result.ok(cicd_service.test_provider(db, user, provider_id))


# ---------------------------------------------------------------- inbound webhook


@router.post("/webhooks/{provider}", response_model=Result)
def provider_webhook(
    db: DbDep,
    provider: str,
    x_provider_token: Annotated[str | None, Header(alias="X-Provider-Token")] = None,
    payload: Any = Body(default=None),
):
    return Result.ok(cicd_service.handle_webhook(db, provider, x_provider_token, payload))


# ---------------------------------------------------------------- releases


@release_router.get("", response_model=Result)
def list_releases(
    db: DbDep,
    user: UserDep,
    status: str | None = None,
    app: str | None = None,
    env: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(cicd_service.list_releases(
        db, user, {"status": status, "app": app, "env": env}, page, size
    ))


@release_router.post("", response_model=Result)
def create_release(db: DbDep, user: UserDep, data: sch.ReleaseCreate):
    return Result.ok(cicd_service.create_release(db, user, data))


@release_router.get("/{release_id}", response_model=Result)
def get_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.get_release(db, user, release_id))


@release_router.post("/{release_id}/deploy", response_model=Result)
def deploy_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.deploy_release(db, user, release_id))


@release_router.post("/{release_id}/canary", response_model=Result)
def canary_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.canary_release(db, user, release_id))


@release_router.post("/{release_id}/promote", response_model=Result)
def promote_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.promote_release(db, user, release_id))


@release_router.post("/{release_id}/fail", response_model=Result)
def fail_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.fail_release(db, user, release_id))


@release_router.post("/{release_id}/rollback", response_model=Result)
def rollback_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.rollback_release(db, user, release_id))


@release_router.post("/{release_id}/cancel", response_model=Result)
def cancel_release(db: DbDep, user: UserDep, release_id: int):
    return Result.ok(cicd_service.cancel_release(db, user, release_id))
