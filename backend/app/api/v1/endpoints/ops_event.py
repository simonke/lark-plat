"""Unified ops-event endpoints (P4 E1): list + detail.

Feature/permission gates live in the service (`ai.events` feature-first, then
`ai:use`); routes stay registered so every openapi key is present. Detail is
404 on missing OR out-of-scope (no existence leak).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.services import ai_service

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=Result)
def list_events(
    db: DbDep,
    user: UserDep,
    source: str | None = None,
    entity_type: str | None = None,
    trace_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(ai_service.list_events(
        db, user, {"source": source, "entity_type": entity_type, "trace_id": trace_id}, page, size
    ))


@router.get("/{event_id}", response_model=Result)
def get_event(db: DbDep, user: UserDep, event_id: int):
    return Result.ok(ai_service.get_event(db, user, event_id))
