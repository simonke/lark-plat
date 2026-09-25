"""AIOps endpoints (P4 E2/E3/E7): ticket assist, KB RAG, feedback/actions.

Three routers share the frozen URL keys: `/ai` (feedback, actions), `/tickets`
(ticket assist sub-routes) and `/kb` (semantic search, answer). Feature/
permission gates live in the service (feature-first, then perm), so routes stay
registered and the openapi surface never shrinks.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.schemas import ai as sch
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["ai"])
ticket_router = APIRouter(prefix="/tickets", tags=["tickets"])
kb_router = APIRouter(prefix="/kb", tags=["kb"])


# ---------------------------------------------------------------- E2 ticket assist


@ticket_router.post("/{ticket_id}/ai/suggest", response_model=Result)
def ticket_suggest(db: DbDep, user: UserDep, ticket_id: int, data: sch.TicketSuggestIn | None = None):
    return Result.ok(ai_service.ticket_suggest(db, user, ticket_id, data))


@ticket_router.get("/{ticket_id}/ai/similar", response_model=Result)
def ticket_similar(
    db: DbDep, user: UserDep, ticket_id: int, limit: Annotated[int, Query(ge=1, le=50)] = 5
):
    return Result.ok(ai_service.ticket_similar(db, user, ticket_id, limit))


# ---------------------------------------------------------------- E3 kb RAG


@kb_router.post("/search/semantic", response_model=Result)
def kb_semantic(db: DbDep, user: UserDep, data: sch.SemanticSearchIn):
    return Result.ok(ai_service.kb_semantic_search(
        db, user, data.q, data.mode, data.limit, data.entity_type
    ))


@kb_router.post("/ai/answer", response_model=Result)
def kb_answer(db: DbDep, user: UserDep, data: sch.AiAnswerIn):
    return Result.ok(ai_service.kb_answer(db, user, data.q, data.limit, data.entity_type))


# ---------------------------------------------------------------- E7/E8 governance


@router.post("/feedback", response_model=Result)
def ai_feedback(db: DbDep, user: UserDep, data: sch.AiFeedbackIn | None = None):
    return Result.ok(ai_service.feedback(db, user, data))


@router.get("/actions", response_model=Result)
def list_ai_actions(
    db: DbDep,
    user: UserDep,
    decision: str | None = None,
    trace_id: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(ai_service.list_actions(db, user, {"decision": decision, "trace_id": trace_id},
                                             page, size))
