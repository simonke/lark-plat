"""Auth endpoints: login/refresh/logout/me/password + P2-3 SSO/providers."""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import RedirectResponse

from app.api.deps import DbDep, OptionalUserDep, UserDep
from app.core.redis_helper import login_rate_limit
from app.core.response import Result
from app.schemas import system as sch
from app.services import auth_service, sso_service

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------- P2-3 identity providers


@router.get("/providers", response_model=Result)
def list_providers(db: DbDep, user: OptionalUserDep):
    """Dual-mode (§3): anonymous -> login-page brief list {code,type,name} incl.
    `local`; caller holding `system:auth:provider` -> management list with masked
    config."""
    if user is not None and user.has_perm("system:auth:provider"):
        return Result.ok(sso_service.list_providers(db))
    return Result.ok(sso_service.login_methods(db))


@router.post("/providers", response_model=Result)
def create_provider(db: DbDep, user: UserDep, data: sch.AuthProviderCreate):
    user.require_perm("system:auth:provider:add")
    return Result.ok(sso_service.create_provider(db, user, data))


@router.put("/providers/{provider_id}", response_model=Result)
def update_provider(db: DbDep, user: UserDep, provider_id: int, data: sch.AuthProviderUpdate):
    user.require_perm("system:auth:provider:edit")
    return Result.ok(sso_service.update_provider(db, user, provider_id, data))


@router.delete("/providers/{provider_id}", response_model=Result)
def delete_provider(db: DbDep, user: UserDep, provider_id: int):
    user.require_perm("system:auth:provider:del")
    return Result.ok(sso_service.delete_provider(db, provider_id))


@router.put("/providers/{provider_id}/status", response_model=Result)
def set_provider_status(db: DbDep, user: UserDep, provider_id: int, data: sch.AuthProviderStatusIn):
    user.require_perm("system:auth:provider:edit")
    return Result.ok(sso_service.set_provider_status(db, provider_id, data.enabled))


@router.post("/providers/{provider_id}/test", response_model=Result)
def test_provider(db: DbDep, user: UserDep, provider_id: int):
    user.require_perm("system:auth:provider:test")
    return Result.ok(sso_service.test_provider(db, provider_id))


@router.post("/ldap/login", response_model=Result)
def ldap_login(db: DbDep, data: sch.LdapLoginIn):
    if not login_rate_limit(data.username):
        return Result.error(429, "too many login attempts, account locked")
    return Result.ok(sso_service.ldap_login(db, data.username, data.password))


@router.get("/oauth/{provider}/login")
def oauth_login(
    request: Request,
    db: DbDep,
    provider: str,
    mode: str | None = Query(default=None, description="json -> return authorize URL"),
):
    base = str(request.base_url)
    url = sso_service.oauth_authorize_url(db, provider, base)
    if mode == "json":
        return Result.ok({"authorize_url": url})
    return RedirectResponse(url=url, status_code=302)


@router.get("/oauth/{provider}/callback")
def oauth_callback(
    request: Request,
    db: DbDep,
    provider: str,
    code: str = Query(default=""),
    state: str = Query(default=""),
    mode: str | None = Query(default=None, description="json -> return tokens"),
):
    result = sso_service.oauth_callback(db, provider, code, state)
    redirect_after = result.pop("redirect_after", None)
    if mode == "json":
        return Result.ok(result)
    if not redirect_after:
        # §3: no configured target -> never 302; fall back to JSON and warn.
        logger.warning("sso: no frontend callback URL configured; returning JSON tokens")
        return Result.ok(result)
    fragment = urlencode(
        {
            "access_token": result["access_token"],
            "refresh_token": result["refresh_token"],
            "token_type": result["token_type"],
        }
    )
    return RedirectResponse(url=f"{redirect_after}#{fragment}", status_code=302)
