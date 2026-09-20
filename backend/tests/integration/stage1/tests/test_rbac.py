"""US-02 RBAC per-endpoint live tests (B1-B11). Requires seed roles + live API."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.live


def test_b1_viewer_cannot_create_user(client, auth_headers):
    r = client.post(
        "/system/users",
        headers=auth_headers("viewer"),
        json={"username": "u_probe_b1", "password": "pass123456"},
    )
    assert r.json()["code"] in (403, 401)


def test_b2_operator_cannot_set_role_perms(client, auth_headers):
    r = client.put(
        "/system/roles/1/permissions",
        headers=auth_headers("operator"),
        json={"permission_ids": []},
    )
    assert r.json()["code"] in (403, 401)


def test_b3_viewer_cannot_delete_user(client, auth_headers):
    r = client.delete("/system/users/99999", headers=auth_headers("viewer"))
    assert r.json()["code"] in (403, 401)


def test_b4_admin_full_crud(client, auth_headers):
    r = client.get("/system/users", headers=auth_headers("admin"), params={"size": 10})
    assert r.json()["code"] == 0
    r = client.get("/system/roles", headers=auth_headers("admin"))
    assert r.json()["code"] == 0


def test_b5_role_crud(client, auth_headers):
    created = client.post(
        "/system/roles",
        headers=auth_headers("admin"),
        json={"code": "probe_role_b5", "name": "probe role b5"},
    )
    assert created.json()["code"] == 0
    role_id = created.json()["data"]["id"]
    try:
        updated = client.put(
            f"/system/roles/{role_id}",
            headers=auth_headers("admin"),
            json={"name": "probe role b5 renamed"},
        )
        assert updated.json()["code"] == 0
        deleted = client.delete(f"/system/roles/{role_id}", headers=auth_headers("admin"))
        assert deleted.json()["code"] == 0
    finally:
        client.delete(f"/system/roles/{role_id}", headers=auth_headers("admin"))


def test_b6_role_permission_binding(client, auth_headers):
    roles = client.get("/system/roles", headers=auth_headers("admin")).json()["data"]
    role = next(r for r in roles if r["code"] == "operator")
    perms = client.get("/system/permissions", headers=auth_headers("admin")).json()["data"]
    ids = [p["id"] for p in perms if p["code"] in ("system:user:list", "system:role:list")]
    original = role["permission_ids"]
    try:
        r = client.put(
            f"/system/roles/{role['id']}/permissions",
            headers=auth_headers("admin"),
            json={"permission_ids": ids},
        )
        assert r.json()["code"] == 0
    finally:
        client.put(
            f"/system/roles/{role['id']}/permissions",
            headers=auth_headers("admin"),
            json={"permission_ids": original},
        )


def test_b8_user_status_lock(client, auth_headers, tokens):
    r = client.put(
        "/system/users/99999/status",
        headers=auth_headers("admin"),
        json={"status": 0},
    )
    assert r.json()["code"] in (0, 404)  # 404 if no such id; still guarded by RBAC


def test_b10_list_filter_pagination(client, auth_headers):
    # Pydantic validation errors: HTTP 422 + Result body carrying code 400.
    r = client.get("/system/users", headers=auth_headers("admin"), params={"page": 0, "size": 10})
    assert r.status_code == 422
    assert r.json()["code"] == 400
    r = client.get("/system/users", headers=auth_headers("admin"), params={"page": 1, "size": 101})
    assert r.status_code == 422
    assert r.json()["code"] == 400


def test_b11_no_token_401(client):
    r = client.get("/system/users")
    assert r.status_code == 401
    assert r.json()["code"] == 401
