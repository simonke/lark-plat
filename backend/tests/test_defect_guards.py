"""Regression guards for stage-1 live A~E defects (D3-1/D3-2/D3-3/D11-1).

Found by integration tester on the live stack; these unit guards pin the
fixed behaviour so the fixes cannot silently regress (strict-encoded xfail
in the live suite tracks the same contract).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from app.api import deps
from app.services import asset_service


# ---------------------------------------------------------------- D3-1


def test_host_search_applies_empty_group_ids_deny():
    """D3-1: empty visible-group list must default-deny (no hosts), not pass all.

    Regression: `if filters.get("group_ids"):` treated [] as "no filter", so an
    unbound viewer saw every host (US-03 violation).
    """
    src = inspect.getsource(asset_service.HostRepository)
    import re

    assert re.search(r"group_ids.*is not None", src), (
        "HostRepository.search must distinguish empty list (deny) from missing (no filter)"
    )


# ---------------------------------------------------------------- D3-2


def test_group_tree_filters_by_user_visible_groups():
    """D3-2: non-admin /assets/groups/tree must exclude groups outside data scope."""
    groups = [
        SimpleNamespace(id=1, parent_id=0, name="组A", sort=0, remark="", created_at=None, updated_at=None),
        SimpleNamespace(id=2, parent_id=0, name="组B", sort=10, remark="", created_at=None, updated_at=None),
    ]

    class FakeRepo:
        def all_tree(self):
            return groups

    monkey = pytest.MonkeyPatch()
    monkey.setattr(asset_service, "GroupRepository", lambda db: FakeRepo())
    try:
        user = SimpleNamespace(is_admin=False, visible_group_ids=[1])
        tree = asset_service.group_tree(SimpleNamespace(), user)
    finally:
        monkey.undo()

    names = [g["name"] for g in tree]
    assert names == ["组A"], f"operator must only see groupA, got {names}"


def test_group_tree_admin_sees_all_groups():
    monkey = pytest.MonkeyPatch()
    groups = [
        SimpleNamespace(id=1, parent_id=0, name="组A", sort=0, remark="", created_at=None, updated_at=None),
        SimpleNamespace(id=2, parent_id=0, name="组B", sort=10, remark="", created_at=None, updated_at=None),
    ]
    monkey.setattr(asset_service, "GroupRepository", lambda db: SimpleNamespace(all_tree=lambda: groups))
    try:
        admin = SimpleNamespace(is_admin=True, visible_group_ids=[])
        tree = asset_service.group_tree(SimpleNamespace(), admin)
    finally:
        monkey.undo()
    assert {g["name"] for g in tree} == {"组A", "组B"}


# ---------------------------------------------------------------- D3-3


def test_jsonb_casts_use_typeengine_not_string():
    """D3-3: cast must receive a TypeEngine; string "text" raised TypeError -> 500."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sources = {
        "asset_service": (root / "app" / "services" / "asset_service.py").read_text(encoding="utf-8"),
        "repositories": (root / "app" / "repositories" / "__init__.py").read_text(encoding="utf-8"),
    }
    for name, src in sources.items():
        bad = [m.group(0) for m in re.finditer(r"cast\([\"']text[\"']\)", src)]
        assert not bad, f"{name}: cast('text') string usage must be removed (D3-3), found {bad}"


# ---------------------------------------------------------------- D11-1


def test_get_current_user_sets_audit_user_on_request():
    """D11-1: authenticated requests must expose request.state.audit_user so
    the audit middleware can record the operator identity."""
    request = SimpleNamespace(state=SimpleNamespace(), app=SimpleNamespace(state=SimpleNamespace(redis=None)))
    user = SimpleNamespace(id=1, username="admin", status=1, deleted=0, is_admin=1)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(deps, "decode_token", lambda token, expected_type=None: {"sub": "1"})
    monkey.setattr(deps, "UserRepository", lambda db: SimpleNamespace(get=lambda i: user))
    monkey.setattr(deps, "_role_ids", lambda db, uid: [1])
    monkey.setattr(deps, "PermissionRepository", lambda db: SimpleNamespace(codes_by_user=lambda uid: ["a"]))
    monkey.setattr(deps, "RoleRepository", lambda db: SimpleNamespace(visible_group_ids=lambda rids: []))
    try:
        cu = deps.get_current_user(request, SimpleNamespace(), "Bearer abc")
    finally:
        monkey.undo()

    assert request.state.audit_user is user
    assert cu.username == "admin"
