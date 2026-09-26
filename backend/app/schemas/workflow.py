"""Pydantic schemas - workflow / Playbook (P3-4, input only).

Outputs are plain dicts assembled by ``workflow_service`` (mirrors
``cmdb_service``), so only request bodies live here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError

from app.db.models.workflow import WORKFLOW_KINDS


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    definition: dict | None = None
    # E5 (P5): discriminator so the SAME engine serves workflow + playbook. Validated
    # against the `WORKFLOW_KINDS` single source (never an inline literal); default
    # `None` => `create_workflow` falls back to the server default `'workflow'`.
    kind: str | None = None

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str | None) -> str | None:
        if value is not None and value not in WORKFLOW_KINDS:
            raise PydanticCustomError(
                "workflow_kind",
                "kind must be one of {kinds}",
                {"kinds": list(WORKFLOW_KINDS)},
            )
        return value


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    enabled: int | None = Field(default=None, ge=0, le=1)


class WorkflowVersionCreate(BaseModel):
    definition: dict
    change_log: str = ""


class WorkflowRollbackIn(BaseModel):
    version: int = Field(ge=1)


class WorkflowRunIn(BaseModel):
    trigger_type: str = "manual"
    trigger_ref: dict | None = None
    context: dict | None = None


class PlaybookSuggestIn(BaseModel):
    goal: str = Field(min_length=1, max_length=256)
    context: str = ""
