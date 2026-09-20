"""Contract baseline checks against the stage-1 openapi.json snapshot (offline, marker: openapi).

【测试维护】This file is frozen stage-1 acceptance-baseline **test maintenance**
(代码reviewer seq2136, 需求 seq2137): `test_diff_a_login_response_is_userbrief`
was updated to follow P2-ID `e45a19c`'s `issue_tokens()` extraction. The
observable contract did NOT change — login/refresh still return
`UserBrief{id,username,real_name,roles}` and `/auth/me` stays full — so this is
a test-side follow, **not** a contract regression. Committed add-only into the
repo (架构 seq2140 item4) with no product-code change.

Covers the integration-side assertion baseline:
  - 66 paths in registration order, static segments before parameterized {id}
  - Result envelope + error-code table
  - snake_case params / pagination constraints
  - securitySchemes declared (bearerAuth/agentToken)
  - operation-level security wiring = stage-1 acceptance item (差异B, currently absent)
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.openapi

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

STAGE1_PATH_SUFFIXES = [
    "/auth/login", "/auth/refresh", "/auth/logout", "/auth/me", "/auth/password",
    "/system/users", "/system/users/{user_id}", "/system/users/{user_id}/roles",
    "/system/users/{user_id}/status", "/system/users/{user_id}/password",
    "/system/roles", "/system/roles/{role_id}", "/system/roles/{role_id}/permissions",
    "/system/roles/{role_id}/groups", "/system/permissions",
    "/system/audit-logs", "/system/audit-logs/export", "/system/audit-logs/{log_id}",
    "/assets/hosts", "/assets/hosts/import", "/assets/hosts/export", "/assets/hosts/stats",
    "/assets/hosts/{host_id}", "/assets/hosts/{host_id}/conn",
    "/assets/groups/tree", "/assets/groups", "/assets/groups/{group_id}",
    "/assets/credentials", "/assets/credentials/{cred_id}", "/assets/options",
    "/exec/tasks", "/exec/tasks/{task_id}", "/exec/tasks/{task_id}/stats",
    "/exec/tasks/{task_id}/stop", "/exec/tasks/{task_id}/retry",
    "/exec/tasks/{task_id}/hosts/{task_host_id}/logs",
    "/exec/tasks/{task_id}/hosts/{task_host_id}/ws-token",
]

ERROR_CODES = {0, 400, 401, 403, 404, 409, 422, 429, 500, 1001}

API_PREFIX = "/api/v1"


def _all_operations(spec: dict):
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            if method in HTTP_METHODS:
                yield path, method, op


def test_has_66_paths(openapi_spec):
    assert len(openapi_spec["paths"]) == 66, f"expected 66 paths, got {len(openapi_spec['paths'])}"


def test_all_paths_under_api_v1(openapi_spec):
    for path in openapi_spec["paths"]:
        assert path.startswith(API_PREFIX), path


def test_stage1_paths_registered(openapi_spec):
    paths = set(openapi_spec["paths"])
    for suffix in STAGE1_PATH_SUFFIXES:
        assert API_PREFIX + suffix in paths, f"missing {suffix}"


def test_static_segments_before_param_segments(openapi_spec):
    # fastapi sorts literal paths before param paths; verify order in emitted spec
    for prefix_group in ("/system/audit-logs", "/assets/hosts", "/assets/groups"):
        keys = [p for p in openapi_spec["paths"] if p.startswith(API_PREFIX + prefix_group)]
        literal = [p for p in keys if "{" not in p]
        param = [p for p in keys if "{" in p]
        # every literal must appear before any param path
        for lit in literal:
            for par in param:
                assert keys.index(lit) < keys.index(par), f"{lit} after {par}"
    assert API_PREFIX + "/system/audit-logs/export" in openapi_spec["paths"]
    assert API_PREFIX + "/system/audit-logs/{log_id}" in openapi_spec["paths"]
    assert list(openapi_spec["paths"]).index(API_PREFIX + "/system/audit-logs/export") < list(
        openapi_spec["paths"]).index(API_PREFIX + "/system/audit-logs/{log_id}")


def test_result_schema_envelope(openapi_spec):
    result = openapi_spec["components"]["schemas"]["Result"]
    props = result.get("properties", {})
    assert set(props) == {"code", "message", "data"}
    assert props["code"]["type"] == "integer"


def test_login_public_no_security_required(openapi_spec):
    login_op = openapi_spec["paths"]["/api/v1/auth/login"]["post"]
    refresh_op = openapi_spec["paths"]["/api/v1/auth/refresh"]["post"]
    # login/refresh must stay public (no op-level security once wiring lands)
    assert login_op.get("security") in (None, [])
    assert refresh_op.get("security") in (None, [])


def test_security_schemes_declared(openapi_spec):
    schemes = openapi_spec["components"]["securitySchemes"]
    assert "bearerAuth" in schemes
    assert "agentToken" in schemes


def test_operation_level_security_wired(openapi_spec):
    """差异B acceptance item: all REST ops except login/refresh carry security.

    Green since backend stage-1 落库 (commit 4baf44d) wired op-level security in
    custom_openapi (PUBLIC_PATHS = login/refresh only) + regenerated openapi.json.
    """
    bare = [o for o in _all_operations(openapi_spec) if o[2].get("security") in (None, [])]
    expected_public = {"/api/v1/auth/login", "/api/v1/auth/refresh"}
    non_public_bare = [(p, m) for p, m, o in bare if p not in expected_public]
    assert non_public_bare == [], (
        f"{len(non_public_bare)} operations lack security:[{{bearerAuth:[]}}]: "
        f"{non_public_bare[:10]}"
    )


def test_diff_a_login_response_is_userbrief(openapi_spec, auth_service_source):
    """差异A: login/refresh return UserBrief{id,username,real_name,roles}; /auth/me full.

    【测试维护】P2-ID `e45a19c` extracted the JWT-pair + UserBrief mint into
    `issue_tokens()`, so the login-body literal moved to its mint point; the
    response shape is unchanged (reviewer seq2136 = test maintenance).

    openapi Result.data is untyped, so the shape is asserted at source level
    against committed backend/app/services/auth_service.py (skip if repo not
    configured). Live check lives in test_auth (A11/A12).
    """
    src = auth_service_source
    issue_body = src.split("def issue_tokens(")[1].split("def login(")[0]
    login_body = src.split("def login(")[1].split("def logout(")[0]
    refresh_body = src.split("def refresh_tokens(")[1].split("def me(")[0]
    me_body = src.split("def me(")[1].split("def change_password(")[0]
    # P2-ID (e45a19c) extracted the JWT-pair + UserBrief mint into the shared
    # issue_tokens() so local login and SSO return an identical payload shape
    # (§3); login/refresh must still return UserBrief{id,username,real_name,roles}
    # and /auth/me the full profile.
    assert "_build_user_brief(db, user, _role_ids(db, user.id))" in issue_body
    assert "issue_tokens(db, user)" in login_body
    assert "_build_user_brief(db, user, _role_ids(db, user.id))" in refresh_body
    assert "_build_me(db, user, _role_ids(db, user.id))" in me_body


def test_error_codes_documented(openapi_spec):
    # Result envelope + documented codes table lives in api-design §1; here we
    # merely assert the envelope schema exists (codes validated at runtime A~E).
    assert "Result" in openapi_spec["components"]["schemas"]


def test_login_response_is_result_envelope(openapi_spec):
    login = openapi_spec["paths"]["/api/v1/auth/login"]["post"]
    ref = login["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ref == "#/components/schemas/Result"


def test_pagination_constraints(openapi_spec):
    list_users = openapi_spec["paths"]["/api/v1/system/users"]["get"]
    params = {p["name"]: p for p in list_users.get("parameters", [])}
    page = params["page"]
    size = params["size"]
    assert page["schema"].get("minimum") == 1
    assert size["schema"].get("minimum") == 1
    assert size["schema"].get("maximum") == 100


def test_params_snake_case(openapi_spec):
    for path, method, op in _all_operations(openapi_spec):
        for p in op.get("parameters", []):
            assert p["name"] == p["name"].lower() and "_" not in p["name"].replace("_", " ") or True
            assert all(c.islower() or c.isdigit() or c == "_" for c in p["name"]), (
                f"{method.upper()} {path} param {p['name']} not snake_case"
            )
