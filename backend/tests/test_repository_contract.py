"""Repository interface contracts (guard against regressions).

system_service.permission_tree() depends on PermissionRepository.tree(); the
same class must expose every method services call so endpoint paths cannot
500 on missing repository methods.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.db.models import Permission
from app.repositories import PermissionRepository
from app.services import system_service


def test_permission_repository_exposes_tree_method():
    """Regression guard: /system/permissions 500 when tree() is missing."""
    assert hasattr(PermissionRepository, "tree"), "PermissionRepository.tree() must exist"
    assert callable(PermissionRepository.tree)


def test_permission_tree_orders_by_sort_then_id():
    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def unique(self):
            return self

        def all(self):
            return self._rows

    class FakeSession:
        def scalars(self, stmt):
            return FakeScalars(None)

        def execute(self, stmt):
            return FakeScalars(None)

    # Spy on the SELECT built by tree(): must order by sort, id.
    from sqlalchemy import select

    calls: list[object] = []

    class FakeScalarsSpy:
        def __init__(self, stmt):
            calls.append(stmt)

        def unique(self):
            return self

        def all(self):
            return []

    class SpySession:
        def scalars(self, stmt):
            return FakeScalarsSpy(stmt)

        def execute(self, stmt):
            return FakeScalarsSpy(stmt)

    PermissionRepository(SpySession()).tree()
    assert calls, "tree() must build a SELECT"

    import sqlalchemy as sa

    ordered = calls[0]._order_by_clauses
    cols = [c.key for c in ordered]
    assert cols[0] == "sort" and cols[1] == "id", f"tree() must order by sort,id got {cols}"


def test_permission_tree_service_builds_parent_child():
    nodes = [
        SimpleNamespace(id=1, parent_id=0, code="root:list", name="根", type="menu",
                        path="/root", icon="X", sort=0, created_at=None, updated_at=None),
        SimpleNamespace(id=2, parent_id=1, code="root:add", name="子", type="button",
                        path="", icon="", sort=10, created_at=None, updated_at=None),
    ]
    class FakeRepo:
        def tree(self):
            return nodes

    monkey = pytest.MonkeyPatch()
    monkey.setattr(system_service, "PermissionRepository", lambda db: FakeRepo())
    try:
        tree = system_service.permission_tree(SimpleNamespace())
    finally:
        monkey.undo()

    assert len(tree) == 1
    assert tree[0]["code"] == "root:list"
    assert tree[0]["children"][0]["code"] == "root:add"
