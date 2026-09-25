"""Pydantic schemas - CI/CD integration (P3-5, input only).

Outputs are plain dicts assembled by ``cicd_service`` (mirrors ``workflow_service``),
so only request bodies live here. ``type`` / ``env`` enums are ``Literal`` so an
invalid value is rejected by FastAPI with **422** before the service runs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProviderType = Literal["gitlab", "jenkins", "generic"]
ReleaseEnv = Literal["dev", "test", "prod"]


class ProviderCreate(BaseModel):
    type: ProviderType
    name: str = Field(min_length=1, max_length=128)
    endpoint: str = Field(min_length=1, max_length=512)
    config: dict | None = None
    enabled: int = Field(default=1, ge=0, le=1)


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    config: dict | None = None
    enabled: int | None = Field(default=None, ge=0, le=1)


class ReleaseCreate(BaseModel):
    provider_id: int = Field(ge=1)
    app: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=64)
    artifact_ref: str | None = Field(default=None, max_length=512)
    env: ReleaseEnv
    target_host_ids: list[int] | None = None
