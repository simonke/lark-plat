"""FastAPI dependencies: current user, permission guard, data-permission scope."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.repositories import PermissionRepository, RoleRepository, UserRepository

DbDep = Annotated[Session, Depends(get_db)]


class CurrentUser:
    """Authenticated principal with resolved permission codes and visible host groups."""

    def __init__(
        self,
        user_id: int,
        username: str,
        is_admin: bool,
        permissions: list[str],
        visible_group_ids: list[int],
    ):
        self.id = user_id
        self.username = username
        self.is_admin = is_admin
        self.permissions = set(permissions)
        self.visible_group_ids = visible_group_ids

    def has_perm(self, code: str) -> bool:
        if self.is_admin:
            return True
        return code in self.permissions

    def require_perm(self, code: str) -> None:
        if not self.has_perm(code):
            raise ForbiddenError(f"permission denied: {code}")

    def require_group(self, group_id: int) -> None:
        if self.is_admin:
            return
        if group_id not in self.visible_group_ids:
            raise ForbiddenError("no data permission for this host group")


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    request: Request,
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    token = _bearer_token(authorization)
    try:
        payload = decode_token(token, "access")
    except ValueError as exc:
        raise UnauthorizedError(str(exc)) from exc

    redis = request.app.state.redis
    if redis is not None:
        jti = payload.get("jti")
        if jti and redis.get(f"bl:{jti}"):
            raise UnauthorizedError("token revoked")

    user_id = int(payload["sub"])
    user_repo = UserRepository(db)
    user = user_repo.get(user_id)
    if user is None or user.status != 1 or user.deleted:
        raise UnauthorizedError("user disabled or missing")

    role_ids = _role_ids(db, user_id)
    perm_repo = PermissionRepository(db)
    role_repo = RoleRepository(db)
    permissions = perm_repo.codes_by_user(user_id) if role_ids else []
    visible_groups = role_repo.visible_group_ids(role_ids)
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        is_admin=bool(user.is_admin),
        permissions=permissions,
        visible_group_ids=visible_groups,
    )


def _role_ids(db: Session, user_id: int) -> list[int]:
    from sqlalchemy import select
    from app.db.models import UserRole

    return list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == user_id)).all())


def require_permission(code: str):
    def checker(user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        user.require_perm(code)
        return user

    return checker


UserDep = Annotated[CurrentUser, Depends(get_current_user)]
