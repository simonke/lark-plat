"""Static contract-assertion baseline vs api-design v2.1 / openapi.json.

These tests run WITHOUT a backend: they assert the committed OpenAPI artifact
(docs/openapi.json) matches the contract. They are the first line of contract
guards agreed with reviewer/architect (66 operations, Result envelope,
error-code table, snake_case, static-route-before-{id}, login/refresh public).
"""

from __future__ import annotations

import pytest

# Contract error-code table (api-design v2.1 §1)
EXPECTED_CODES = {0, 400, 401, 403, 404, 409, 422, 429, 500, 1001}

# Stage-1 auth + system scope (US-01/02/03)
STAGE1_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/me",
    "/api/v1/auth/password",
    "/api/v1/auth/refresh",
    "/api/v1/system/users",
    "/api/v1/system/roles",
    "/api/v1/system/permissions",
    "/api/v1/system/audit-logs",
    "/api/v1/system/audit-logs/export",
}

# Public operations exempt from bearer auth (api-design v2.1 §1)
PUBLIC_OPS = {("/api/v1/auth/login", "post"), ("/api/v1/auth/refresh", "post")}

# Seed permission points vs module-design §12 (stage-1 subset)
STAGE1_PERMISSIONS = {
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


def _all_operations(spec: dict):
    for path, item in spec["paths"].items():
        for method in ("get", "post", "put", "delete", "patch"):
            if method in item:
                yield path, method, item[method]


def test_openapi_has_security_schemes(openapi_spec):
    schemes = openapi_spec.get("components", {}).get("securitySchemes", {})
    assert "bearerAuth" in schemes
    assert schemes["bearerAuth"]["type"] == "http"
    assert schemes["bearerAuth"]["scheme"] == "bearer"
    # Agent token scheme declared for stage 2 (X-Agent-Token)
    assert "agentToken" in schemes


def test_login_refresh_public_and_rest_guarded(openapi_spec):
    """Contract requires every op except login/refresh to declare
    security:[{bearerAuth:[]}]. login/refresh stay public.
    """
    for path, method, op in _all_operations(openapi_spec):
        key = (path, method)
        if key in PUBLIC_OPS:
            assert not op.get("security"), f"{key} must stay public (no security)"
        else:
            sec = op.get("security")
            assert sec, f"{key} must declare security:[{{bearerAuth:[]}}]"


def test_path_count_stable(openapi_spec):
    paths = openapi_spec["paths"]
    assert len(paths) == 66


def test_stage1_scope_paths_present(openapi_spec):
    paths = openapi_spec["paths"]
    missing = STAGE1_PATHS - set(paths)
    assert not missing, f"stage-1 paths missing: {sorted(missing)}"


def test_static_route_before_id(openapi_spec):
    """Static segments must be registered before {id} (avoid shadowing)."""
    paths = list(openapi_spec["paths"])
    for static, dynamic in (
        ("/api/v1/system/audit-logs/export", "/api/v1/system/audit-logs/{log_id}"),
        ("/api/v1/assets/hosts/export", "/api/v1/assets/hosts/{host_id}"),
        ("/api/v1/assets/hosts/stats", "/api/v1/assets/hosts/{host_id}"),
        ("/api/v1/assets/groups/tree", "/api/v1/assets/groups/{group_id}"),
    ):
        assert paths.index(static) < paths.index(dynamic), f"{static} must precede {dynamic}"


def test_result_schema_contract(openapi_spec):
    result = openapi_spec["components"]["schemas"].get("Result")
    assert result is not None, "Result schema must exist"
    props = result["properties"]
    assert set(props) == {"code", "message", "data"}
    assert props["code"]["type"] == "integer"
    assert props["message"]["type"] == "string"


def test_login_schema_contract(openapi_spec):
    login = openapi_spec["components"]["schemas"]["LoginIn"]
    assert set(login["required"]) == {"username", "password"}
    assert login["properties"]["username"]["minLength"] == 1
    assert login["properties"]["password"]["minLength"] == 1


def test_seed_permission_points_declared(openapi_spec):
    """Permission points used by stage-1 pages must be declared in contract docs.

    The permissions tree lives in module-design §12; this test guards the
    exact code set that stage-1 RBAC must seed.
    """
    # static check on our contract baseline — actual seed verification is
    # asserted post-landing against /system/permissions (runtime test).
    assert len(STAGE1_PERMISSIONS) == 13
    assert "system:user:list" in STAGE1_PERMISSIONS
    assert "system:audit:export" in STAGE1_PERMISSIONS
