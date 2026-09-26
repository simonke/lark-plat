"""Workflow endpoints (P3-4): Playbook CRUD/versions + run control.

Static segments register before `{id}` segments. The feature-flag/permission
guards live in the service (routes stay registered so openapi keeps every key,
and the feature gate runs FIRST for any caller).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import workflow as sch
from app.services import workflow_service

router = APIRouter(prefix="/workflows", tags=["workflows"])
run_router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@router.get("", response_model=Result)
def list_workflows(
    db: DbDep,
    user: UserDep,
    name: str | None = None,
    enabled: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(workflow_service.list_workflows(
        db, user, {"name": name, "enabled": enabled}, page, size
    ))


@router.post("", response_model=Result)
def create_workflow(db: DbDep, user: UserDep, data: sch.WorkflowCreate):
    return Result.ok(workflow_service.create_workflow(db, user, data))


# P5 E5: static segment MUST precede `/{workflow_id}` (avoids the int-coerce 422).
@router.post("/ai/suggest", response_model=Result)
def suggest_playbook(db: DbDep, user: UserDep, data: sch.PlaybookSuggestIn):
    return Result.ok(workflow_service.suggest_playbook(db, user, data))


@router.get("/{workflow_id}", response_model=Result)
def get_workflow(db: DbDep, user: UserDep, workflow_id: int):
    return Result.ok(workflow_service.get_workflow(db, user, workflow_id))


@router.put("/{workflow_id}", response_model=Result)
def update_workflow(db: DbDep, user: UserDep, workflow_id: int, data: sch.WorkflowUpdate):
    return Result.ok(workflow_service.update_workflow(db, user, workflow_id, data))


@router.delete("/{workflow_id}", response_model=Result)
def delete_workflow(db: DbDep, user: UserDep, workflow_id: int):
    workflow_service.delete_workflow(db, user, workflow_id)
    return Result.ok()


@router.post("/{workflow_id}/versions", response_model=Result)
def create_version(db: DbDep, user: UserDep, workflow_id: int, data: sch.WorkflowVersionCreate):
    return Result.ok(workflow_service.create_version(db, user, workflow_id, data))


@router.get("/{workflow_id}/versions", response_model=Result)
def list_versions(db: DbDep, user: UserDep, workflow_id: int):
    return Result.ok(workflow_service.list_versions(db, user, workflow_id))


@router.post("/{workflow_id}/rollback", response_model=Result)
def rollback_workflow(db: DbDep, user: UserDep, workflow_id: int, data: sch.WorkflowRollbackIn):
    return Result.ok(workflow_service.rollback_workflow(db, user, workflow_id, data.version))


@router.post("/{workflow_id}/run", response_model=Result)
def run_workflow(
    db: DbDep,
    user: UserDep,
    workflow_id: int,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    data: sch.WorkflowRunIn | None = None,
):
    return Result.ok(
        workflow_service.run_workflow(db, user, workflow_id, idempotency_key, data)
    )


@run_router.get("", response_model=Result)
def list_runs(
    db: DbDep,
    user: UserDep,
    workflow_id: int | None = None,
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(workflow_service.list_runs(
        db, user, {"workflow_id": workflow_id, "status": status}, page, size
    ))


@run_router.get("/{run_id}", response_model=Result)
def get_run(db: DbDep, user: UserDep, run_id: int):
    return Result.ok(workflow_service.get_run(db, user, run_id))


@run_router.get("/{run_id}/ws-token", response_model=Result)
def run_ws_token(db: DbDep, user: UserDep, run_id: int):
    return Result.ok(workflow_service.run_ws_token(db, user, run_id))


@run_router.post("/{run_id}/callback/{node_key}", response_model=Result)
def callback_node(
    db: DbDep,
    run_id: int,
    node_key: str,
    x_callback_token: Annotated[str | None, Header(alias="X-Callback-Token")] = None,
    payload: Any = Body(default=None),
):
    return Result.ok(
        workflow_service.callback_node(db, run_id, node_key, x_callback_token, payload)
    )


@run_router.post("/{run_id}/cancel", response_model=Result)
def cancel_run(db: DbDep, user: UserDep, run_id: int):
    return Result.ok(workflow_service.cancel_run(db, user, run_id))


@run_router.post("/{run_id}/retry", response_model=Result)
def retry_run(db: DbDep, user: UserDep, run_id: int):
    return Result.ok(workflow_service.retry_run(db, user, run_id))
