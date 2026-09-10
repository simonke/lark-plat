"""Seed-data existence contract (module-design §12).

Static assertion against app/db/seed.py (DB-free): the RBAC baseline must
declare the full permission-point tree (18 menus + 53 buttons post P2-MA) and
the 3 builtin roles. Runtime presence is verified by integration against
/system/permissions; this guards the declared contract itself.
"""

from __future__ import annotations

from app.db.seed import DEFAULT_ROLES, PERMISSION_TREE


MONITOR_CODES = {
    "monitor:metric:view",
    "monitor:alert:list", "monitor:alert:view", "monitor:alert:ack", "monitor:alert:resolve",
    "monitor:rule:list", "monitor:rule:add", "monitor:rule:edit", "monitor:rule:del",
    "monitor:rule:status", "monitor:rule:test",
}


def test_seed_tree_permission_points():
    menus = [node[0] for node in PERMISSION_TREE]
    buttons = [child[0] for node in PERMISSION_TREE for child in node[5]]
    assert len(menus) == 18
    assert len(buttons) == 53
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


def test_p2ma_monitor_permission_codes_covered_by_seed():
    """P2-MA monitor permission points must be seeded (add-only over baseline)."""
    seeded = {node[0] for node in PERMISSION_TREE} | {
        child[0] for node in PERMISSION_TREE for child in node[5]
    }
    missing = MONITOR_CODES - seeded
    assert not missing, f"P2-MA monitor permission points missing from seed: {sorted(missing)}"


def test_p2ma_monitor_menu_route_paths_frozen():
    """Route paths in the permission tree are the authority for frontend routing."""
    path_by_code = {node[0]: node[3] for node in PERMISSION_TREE}
    assert path_by_code["monitor:metric:view"] == "/monitor/dashboard"
    assert path_by_code["monitor:alert:list"] == "/monitor/alerts"
    assert path_by_code["monitor:rule:list"] == "/monitor/rules"


def test_p2ma_operator_role_bindings():
    """Frozen operator binding: full alert handling + rule ops except delete."""
    op = set(DEFAULT_ROLES["operator"]["permissions"])
    assert MONITOR_CODES - {"monitor:rule:del"} <= op
    assert "monitor:rule:del" not in op


def test_p2ma_viewer_role_bindings():
    """Frozen viewer binding: monitor read-only group (no buttons)."""
    view = set(DEFAULT_ROLES["viewer"]["permissions"])
    assert {"monitor:metric:view", "monitor:alert:list", "monitor:alert:view", "monitor:rule:list"} <= view
    assert not (view & {"monitor:alert:ack", "monitor:alert:resolve",
                        "monitor:rule:add", "monitor:rule:edit", "monitor:rule:del",
                        "monitor:rule:status", "monitor:rule:test"})


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
    assert all(
        p.endswith(":list")
        or p in {
            "dashboard:view", "exec:task:log", "terminal:view",
            "monitor:metric:view", "monitor:alert:view",
        }
        for p in view
    )


def test_admin_user_bound_to_admin_role_in_seed_source():
    """Seed 方案 a: bootstrap admin must be bound to the admin role (UserRole).

    /auth/me therefore returns roles=['admin'] + full permissions (60) per
    contract §2 full-profile shape; is_admin=1 retained as bypass.
    """
    import inspect

    from app.db.seed import seed_admin_user

    src = inspect.getsource(seed_admin_user)
    assert "Role" in src
    assert 'code == "admin"' in src
    assert "UserRole" in src
    assert "Role.code" in src


def test_seed_bootstraps_operator_and_viewer_users():
    """Seed gap: stage-1 live A~E needed operator/viewer principals (three-state
    per module-design §12); the seed must create them bound to default roles."""
    import inspect as _inspect

    from app.db.seed import seed_bootstrap_users

    src = _inspect.getsource(seed_bootstrap_users)
    for role_code in ("admin", "operator", "viewer"):
        assert role_code in src, f"seed_bootstrap_users must cover '{role_code}'"
    assert "UserRole" in src
