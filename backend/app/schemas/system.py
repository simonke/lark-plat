"""Pydantic schemas - auth & system management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    real_name: str
    phone: str
    email: str
    status: int
    last_login_at: datetime | None = None


class UserMe(BaseModel):
    id: int
    username: str
    real_name: str
    roles: list[RoleBrief] = []
    permissions: list[str] = []
    visible_group_ids: list[int] = []
    is_admin: bool = False


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    real_name: str = ""
    phone: str = ""
    email: EmailStr | str = ""
    role_ids: list[int] = []
    status: int = 1


class UserUpdate(BaseModel):
    real_name: str | None = None
    phone: str | None = None
    email: EmailStr | str | None = None
    status: int | None = None


class UserRolesIn(BaseModel):
    role_ids: list[int] = []


class UserStatusIn(BaseModel):
    status: int = Field(ge=0, le=1)


class ResetPasswordIn(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class RoleCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    remark: str = ""


class RoleUpdate(BaseModel):
    name: str | None = None
    remark: str | None = None


class RoleIdsIn(BaseModel):
    permission_ids: list[int] = []


class GroupIdsIn(BaseModel):
    group_ids: list[int] = []


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    remark: str


class PermissionNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: int
    code: str
    name: str
    type: str
    path: str
    icon: str
    sort: int
    children: list["PermissionNode"] = []


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int | None
    username: str
    module: str
    action: str
    method: str
    path: str
    params: dict | None
    ip: str
    user_agent: str
    status: int
    cost_ms: int
    trace_id: str
    created_at: datetime
