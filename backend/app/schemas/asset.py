"""Pydantic schemas - asset management."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GroupCreate(BaseModel):
    parent_id: int | None = None
    name: str = Field(min_length=1, max_length=64)
    sort: int = 0
    remark: str = ""


class GroupUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    sort: int | None = None
    remark: str | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: int
    name: str
    sort: int
    remark: str
    children: list["GroupOut"] = []


class HostCreate(BaseModel):
    hostname: str = Field(min_length=1, max_length=128)
    ip: str = Field(min_length=1, max_length=64)
    os_type: str = "linux"
    os_version: str = ""
    group_id: int | None = None
    env: str = "prod"
    tags: list[str] | None = None
    connector: str = "agent"
    sensitivity_level: str = "normal"
    remark: str = ""


class HostUpdate(BaseModel):
    hostname: str | None = None
    ip: str | None = None
    os_type: str | None = None
    os_version: str | None = None
    group_id: int | None = None
    env: str | None = None
    tags: list[str] | None = None
    connector: str | None = None
    sensitivity_level: str | None = None
    remark: str | None = None


def _normalize_tags(value: Any) -> list[str]:
    """Accept legacy shapes (None / "a,b" / {"label": "a;b"} / list) as list[str]."""
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.replace(";", ",").split(",") if t.strip()]
    if isinstance(value, dict):
        merged: list[str] = []
        for v in value.values():
            merged.extend(_normalize_tags(v))
        return merged
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for v in value:
            out.extend(_normalize_tags(v))
        return out
    return [_normalize_tags(value)[0]] if _normalize_tags(value) else []


class HostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hostname: str
    ip: str
    os_type: str
    os_version: str
    group_id: int | None
    group_name: str = ""
    env: str
    tags: list[str] = []
    sensitivity_level: str = "normal"
    status: str
    connector: str
    agent_id: str | None
    agent_version: str
    last_heartbeat_at: datetime | None
    remark: str
    created_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def _tags_as_list(cls, v: Any) -> list[str]:
        return _normalize_tags(v)


class ConnResult(BaseModel):
    ok: bool
    latency_ms: int
    detail: str


class CredentialCreate(BaseModel):
    host_id: int
    type: str = "password"
    username: str = Field(min_length=1, max_length=64)
    secret: str | None = None
    key: str | None = None
    passphrase: str | None = None


class CredentialUpdate(BaseModel):
    type: str | None = None
    username: str | None = None
    secret: str | None = None
    key: str | None = None
    passphrase: str | None = None


class CredentialOut(BaseModel):
    id: int
    host_id: int
    hostname: str = ""
    ip: str = ""
    host_hostname: str = ""
    type: str
    username: str
    secret_mask: str | None
    key_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HostStats(BaseModel):
    total: int
    online: int
    offline: int
    by_env: dict[str, int]


class ImportResult(BaseModel):
    success: int
    failed: list[dict]
