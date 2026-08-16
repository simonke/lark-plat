"""Seed-data existence contract (module-design §12).

Static assertion against app/db/seed.py (DB-free): the RBAC baseline must
declare the full 60-permission-point tree (15 menus + 45 buttons) and the 3
builtin roles. Runtime presence is verified by integration against
/system/permissions; this guards the declared contract itself.
"""

from __future__ import annotations

from app.db.seed import DEFAULT_ROLES, PERMISSION_TREE


def test_seed_tree_has_60_permission_points():
    menus = [node[0] for node in PERMISSION_TREE]
    buttons = [child[0] for node in PERMISSION_TREE for child in node[5]]
    assert len(menus) == 15
    assert len(buttons) == 45
    assert len(set(menus)) == len(menus)
    assert len(set(buttons)) == len(buttons)


def test_seed_tree_has_three_builtin_roles():
    assert set(DEFAULT_ROLES) == {"admin", "operator", "viewer"}


def test_stage1_permission_codes_covered_by_seed():
    seeded = {node[0] for node in PERMISSION_TREE} | {
        child[0] for node in PERMISSION_TREE for child in node[5]
    }
    stage1 = {
        "system:user:list",
        "system:user:add",
        "system:user:edit",
        "system:user:del",
        "system:user:role",
        "system:role:list",
        "system:role:add",
        "system:role:edit",
        "system:role:del",
        "system:role:perm",
        "system:role:group",
        "system:audit:list",
        "system:audit:export",
    }
    assert stage1 <= seeded


def test_admin_role_binds_all_permissions():
    all_codes = {node[0] for node in PERMISSION_TREE} | {
        child[0] for node in PERMISSION_TREE for child in node[5]
    }
    assert set(DEFAULT_ROLES["admin"]["permissions"]) == all_codes


def test_operator_role_is_operational_only():
    op = set(DEFAULT_ROLES["operator"]["permissions"])
    assert "system:role:del" not in op
    assert "system:user:add" not in op
    assert "exec:task:run" in op


def test_viewer_role_is_read_only():
    view = set(DEFAULT_ROLES["viewer"]["permissions"])
    assert all(p.endswith(":list") or p in {"dashboard:view", "exec:task:log", "terminal:view"} for p in view)
