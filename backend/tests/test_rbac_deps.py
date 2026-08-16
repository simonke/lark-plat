"""RBAC dependency unit tests (US-03): permission gating, admin bypass, 403."""

from __future__ import annotations

import pytest

from app.api.deps import CurrentUser
from app.core.exceptions import ForbiddenError


def _cu(perms: list[str] | None = None, groups: list[int] | None = None, is_admin: bool = False) -> CurrentUser:
    return CurrentUser(
        user_id=1,
        username="bob",
        is_admin=is_admin,
        permissions=perms or [],
        visible_group_ids=groups or [],
    )


def test_admin_has_any_permission():
    cu = _cu(is_admin=True)
    assert cu.has_perm("system:role:del")
    cu.require_perm("anything:at:all")  # must not raise


def test_user_with_permission_passes():
    cu = _cu(perms=["system:user:list"])
    assert cu.has_perm("system:user:list")
    cu.require_perm("system:user:list")


def test_user_without_permission_raises_403():
    cu = _cu(perms=["system:user:list"])
    with pytest.raises(ForbiddenError):
        cu.require_perm("system:role:list")


def test_no_permissions_default_deny():
    cu = _cu(perms=[])
    assert not cu.has_perm("system:user:list")
    with pytest.raises(ForbiddenError):
        cu.require_perm("system:user:list")


def test_require_group_allows_visible_group():
    cu = _cu(groups=[7, 9])
    cu.require_group(9)  # must not raise


def test_require_group_denies_unbound_group():
    cu = _cu(groups=[7])
    with pytest.raises(ForbiddenError):
        cu.require_group(9)


def test_require_group_default_deny_when_no_groups():
    cu = _cu(groups=[])
    with pytest.raises(ForbiddenError):
        cu.require_group(1)


def test_require_group_admin_bypass():
    cu = _cu(is_admin=True, groups=[])
    cu.require_group(12345)  # admin sees everything
