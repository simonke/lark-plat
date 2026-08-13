"""Pydantic schemas - asset management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    parent_id: int = 0
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
    tags: dict | None = None
    connector: str = "agent"
    remark: str = ""


class HostUpdate(BaseModel):
    hostname: str | None = None
    os_type: str | None = None
    os_version: str | None = None
    group_id: int | None = None
    env: str | None = None
    tags: dict | None = None
    connector: str | None = None
    remark: str | None = None


class HostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    hostname: str
    ip: str
    os_type: str
    os_version: str
    group_id: int | None
    env: str
    tags: dict | None
    status: str
    connector: str
    agent_id: str | None
    agent_version: str
    last_heartbeat_at: datetime | None
    remark: str
    created_at: datetime


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
    type: str
    username: str
    secret_mask: str | None
    key_version: int
    updated_at: datetime


class HostStats(BaseModel):
    total: int
    online: int
    offline: int
    by_env: dict[str, int]


class ImportResult(BaseModel):
    success: int
    failed: list[dict]
