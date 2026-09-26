"""P4 AIOps request schemas (add-only)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TicketSuggestIn(BaseModel):
    context: str | None = None
    purpose: str = "ticket_suggest"


class SemanticSearchIn(BaseModel):
    q: str = Field(min_length=1, max_length=512)
    mode: str = "hybrid"  # vector | fts | hybrid
    limit: int = Field(default=10, ge=1, le=50)
    entity_type: str | None = None


class AiAnswerIn(BaseModel):
    q: str = Field(min_length=1, max_length=512)
    limit: int = Field(default=5, ge=1, le=20)
    entity_type: str | None = None


class RcaRunIn(BaseModel):
    # Depth domain is owned by cmdb_service (`0..3`, default 2; `<0`/`>3` -> 422).
    depth: int | None = None


class AiFeedbackIn(BaseModel):
    trace_id: str | None = None
    decision: str = "auto"  # adopted | rejected | auto
    model_name: str | None = None
    model_version: str | None = None
    confidence: float | None = None
    input_snapshot: dict | None = None
    basis_refs: list | None = None
