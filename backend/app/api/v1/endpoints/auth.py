"""Auth endpoints: login/refresh/logout/me/password."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request

from app.api.deps import DbDep, UserDep
from app.core.redis_helper import login_rate_limit
from app.core.response import Result
from app.schemas import system as sch
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Result)
def login(request: Request, db: DbDep, data: sch.LoginIn):
    if not login_rate_limit(data.username):
        return Result.error(429, "too many login attempts, account locked")
    result = auth_service.login(db, data.username, data.password)
    return Result.ok(result)


@router.post("/refresh", response_model=Result)
def refresh(db: DbDep, data: sch.RefreshIn):
    result = auth_service.refresh_tokens(db, data.refresh_token)
    return Result.ok(result)


@router.post("/logout", response_model=Result)
def logout(db: DbDep, authorization: str | None = Header(default=None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token:
        auth_service.logout(db, token)
    return Result.ok()


@router.get("/me", response_model=Result)
def me(db: DbDep, user: UserDep):
    return Result.ok(auth_service.me(db, user.id))


@router.put("/password", response_model=Result)
def change_password(db: DbDep, user: UserDep, data: sch.ChangePasswordIn):
    auth_service.change_password(db, user.id, data.old_password, data.new_password)
    return Result.ok()
