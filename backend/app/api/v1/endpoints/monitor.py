"""Monitor endpoints: metrics, alerts, rules, adapters, events, ingest, WS token."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import monitor_service

router = APIRouter(prefix="/monitor", tags=["monitor"])


# ── Metrics ─────────────────────────────────────────────────────────────────


@router.get("/metrics", response_model=Result)
def query_metrics(
    db: DbDep,
    user: UserDep,
    entity_ids: str | None = None,
    group_id: int | None = None,
    metric_name: str = "",
    start: str | None = None,
    end: str | None = None,
    agg: str = "",
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=500)] = 50,
):
    eid_list = [e.strip() for e in entity_ids.split(",") if e.strip()] if entity_ids else None
    return Result.ok(monitor_service.query_metrics(
        db, user, eid_list, group_id, metric_name, start, end, agg, page, size,
    ))


@router.get("/metrics/current", response_model=Result)
def current_metrics(
    db: DbDep,
    user: UserDep,
    entity_ids: str | None = None,
    metric_name: str | None = None,
):
    eid_list = [e.strip() for e in entity_ids.split(",") if e.strip()] if entity_ids else None
    return Result.ok(monitor_service.current_metrics(db, user, eid_list, metric_name))


# ── Alerts ──────────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=Result)
def list_alerts(
    db: DbDep,
    user: UserDep,
    status: str | None = None,
    severity: str | None = None,
    rule_id: int | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    filters = {}
    if status:
        filters["status"] = status
    if severity:
        filters["severity"] = severity
    if rule_id:
        filters["rule_id"] = rule_id
    return Result.ok(monitor_service.list_alerts(db, user, filters, page, size))


@router.get("/alerts/{alert_id}", response_model=Result)
def get_alert(db: DbDep, user: UserDep, alert_id: int):
    return Result.ok(monitor_service.get_alert(db, user, alert_id))


@router.get("/alerts/{alert_id}/events", response_model=Result)
def alert_events(db: DbDep, user: UserDep, alert_id: int):
    return Result.ok(monitor_service.alert_events(db, user, alert_id))


@router.post("/alerts/{alert_id}/acknowledge", response_model=Result)
def acknowledge_alert(db: DbDep, user: UserDep, alert_id: int, data: schemas.AlertAckIn):
    return Result.ok(monitor_service.acknowledge_alert(db, user, alert_id, data.remark))


@router.post("/alerts/{alert_id}/resolve", response_model=Result)
def resolve_alert(db: DbDep, user: UserDep, alert_id: int, data: schemas.AlertResolveIn):
    return Result.ok(monitor_service.resolve_alert(db, user, alert_id, data.remark))


# ── Rules ───────────────────────────────────────────────────────────────────


@router.get("/rules", response_model=Result)
def list_rules(
    db: DbDep,
    user: UserDep,
    enabled: int | None = None,
    event_kind: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    filters = {}
    if enabled is not None:
        filters["enabled"] = enabled
    if event_kind:
        filters["event_kind"] = event_kind
    return Result.ok(monitor_service.list_rules(db, user, filters, page, size))


@router.post("/rules", response_model=Result)
def create_rule(db: DbDep, user: UserDep, data: schemas.MonRuleCreate):
    return Result.ok(monitor_service.create_rule(db, user, data))


@router.put("/rules/{rule_id}", response_model=Result)
def update_rule(db: DbDep, user: UserDep, rule_id: int, data: schemas.MonRuleUpdate):
    return Result.ok(monitor_service.update_rule(db, user, rule_id, data))


@router.delete("/rules/{rule_id}", response_model=Result)
def delete_rule(db: DbDep, user: UserDep, rule_id: int):
    return Result.ok(monitor_service.delete_rule(db, user, rule_id))


@router.post("/rules/{rule_id}/status", response_model=Result)
def set_rule_status(db: DbDep, user: UserDep, rule_id: int, data: schemas.MonRuleStatusIn):
    return Result.ok(monitor_service.set_rule_status(db, user, rule_id, data.enabled))


@router.post("/rules/{rule_id}/test", response_model=Result)
def test_rule(db: DbDep, user: UserDep, rule_id: int):
    return Result.ok(monitor_service.test_rule(db, user, rule_id))


# ── Adapters ────────────────────────────────────────────────────────────────


@router.get("/adapters", response_model=Result)
def list_adapters(
    db: DbDep,
    user: UserDep,
    enabled: int | None = None,
    type: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(monitor_service.list_adapters(db, user, enabled, type, page, size))


@router.post("/adapters", response_model=Result)
def create_adapter(db: DbDep, user: UserDep, data: schemas.MonAdapterCreate):
    return Result.ok(monitor_service.create_adapter(db, user, data))


@router.put("/adapters/{adapter_id}", response_model=Result)
def update_adapter(db: DbDep, user: UserDep, adapter_id: int, data: schemas.MonAdapterUpdate):
    return Result.ok(monitor_service.update_adapter(db, user, adapter_id, data))


@router.delete("/adapters/{adapter_id}", response_model=Result)
def delete_adapter(db: DbDep, user: UserDep, adapter_id: int):
    return Result.ok(monitor_service.delete_adapter(db, user, adapter_id))


@router.post("/adapters/{adapter_id}/status", response_model=Result)
def set_adapter_status(db: DbDep, user: UserDep, adapter_id: int, data: schemas.MonAdapterStatusIn):
    return Result.ok(monitor_service.set_adapter_status(db, user, adapter_id, data.enabled))


@router.post("/adapters/{adapter_id}/test", response_model=Result)
def test_adapter(db: DbDep, user: UserDep, adapter_id: int):
    return Result.ok(monitor_service.test_adapter(db, user, adapter_id))


# ── Events ──────────────────────────────────────────────────────────────────


@router.get("/events", response_model=Result)
def list_events(
    db: DbDep,
    user: UserDep,
    source: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    filters = {}
    if source:
        filters["source"] = source
    if kind:
        filters["kind"] = kind
    if status:
        filters["status"] = status
    return Result.ok(monitor_service.list_events(db, user, filters, page, size))


@router.get("/events/{event_id}", response_model=Result)
def get_event(db: DbDep, user: UserDep, event_id: int):
    return Result.ok(monitor_service.get_event(db, user, event_id))


# ── Ingest ──────────────────────────────────────────────────────────────────


@router.post("/ingest/{adapter_id}", response_model=Result)
def ingest(db: DbDep, adapter_id: int, payload: dict):
    return Result.ok(monitor_service.ingest(db, adapter_id, payload))


# ── WS token ────────────────────────────────────────────────────────────────


@router.get("/ws-token", response_model=Result)
def ws_token(db: DbDep, user: UserDep):
    return Result.ok(monitor_service.ws_token(db, user))
