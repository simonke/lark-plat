"""Auth service: login/logout/refresh/me/password, login rate limit, audit."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, UnauthorizedError
from app.core.redis_helper import (
    blacklist_access,
    clear_login_failures,
    get_redis,
    record_login_failure,
    revoke_refresh,
    store_refresh,
    validate_refresh,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.repositories import PermissionRepository, RoleRepository, UserRepository


def _role_ids(db: Session, user_id: int) -> list[int]:
    from sqlalchemy import select
    from app.db.models import UserRole

    return list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id)).all())


def _build_me(db: Session, user: User, role_ids: list[int]) -> dict:
    role_repo = RoleRepository(db)
    perm_repo = PermissionRepository(db)
    roles = []
    for rid in role_ids:
        role = role_repo.get(rid)
        if role:
            roles.append({"id": role.id, "code": role.code, "name": role.name})
    permissions = perm_repo.codes_by_user(user.id) if role_ids else []
    visible = role_repo.visible_group_ids(role_ids)
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "roles": roles,
        "permissions": permissions,
        "visible_group_ids": visible,
        "is_admin": bool(user.is_admin),
    }


def login(db: Session, username: str, password: str) -> dict:
    user_repo = UserRepository(db)
    user = user_repo.by_username(username)
    if user is None or user.deleted or user.status != 1:
        raise UnauthorizedError("invalid username or password")
    if not verify_password(password, user.password_hash):
        record_login_failure(username)
        raise UnauthorizedError("invalid username or password")
    clear_login_failures(username)

    access = create_access_token(user.id)
    refresh_payload = decode_token(create_refresh_token(user.id))
    refresh = create_refresh_token(user.id)
    store_refresh(user.id, refresh_payload["jti"])

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": _build_me(db, user, _role_ids(db, user.id)),
    }


def logout(db: Session, access_token: str) -> None:
    try:
        payload = decode_token(access_token, "access")
        blacklist_access(payload["jti"])
        revoke_refresh(int(payload["sub"]))
    except ValueError:
        raise UnauthorizedError("invalid token")


def refresh_tokens(db: Session, refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token, "refresh")
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc
    user_id = int(payload["sub"])
    if not validate_refresh(user_id, payload["jti"]):
        raise UnauthorizedError("refresh token expired or reused")
    user_repo = UserRepository(db)
    user = user_repo.get(user_id)
    if user is None or user.status != 1 or user.deleted:
        raise UnauthorizedError("user disabled or missing")
    access = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    new_payload = decode_token(new_refresh, "refresh")
    store_refresh(user.id, new_payload["jti"])
    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user": _build_me(db, user, _role_ids(db, user.id)),
    }


def me(db: Session, user_id: int) -> dict:
    user_repo = UserRepository(db)
    user = user_repo.get(user_id)
    if user is None:
        raise UnauthorizedError("user not found")
    return _build_me(db, user, _role_ids(db, user.id))


def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> None:
    user_repo = UserRepository(db)
    user = user_repo.get(user_id)
    if user is None:
        raise UnauthorizedError("user not found")
    if not verify_password(old_password, user.password_hash):
        raise BadRequestError("old password incorrect")
    user.password_hash = hash_password(new_password)
    db.commit()
