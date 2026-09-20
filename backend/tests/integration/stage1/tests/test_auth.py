"""US-01 auth & session live tests (A1-A12). Requires live API + seed users."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.live


def _login(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def _fresh_admin(client, creds):
    """Fresh admin login for mutating tests (avoid rotating the shared session token)."""
    user, pwd = creds["admin"]
    resp = _login(client, user, pwd)
    assert resp.status_code == 200 and resp.json()["code"] == 0
    return resp.json()["data"]


def test_a1_login_success(client, creds):
    user, pwd = creds["admin"]
    resp = _login(client, user, pwd)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data) >= {"access_token", "refresh_token", "token_type"}
    assert data["token_type"] == "bearer"


def test_a2_wrong_password(client, creds):
    user, _ = creds["admin"]
    resp = _login(client, user, "definitely-wrong-password")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 401
    assert body["data"] is None


def test_a3_login_lockout(client, auth_headers, creds):
    # Lockout counts failures only for existing users. Create a throwaway user,
    # fail 5x -> 6th attempt returns 429 (HTTP 200 envelope), then clean up.
    name = "lockout_probe_" + uuid.uuid4().hex[:8]
    create = client.post(
        "/system/users",
        headers=auth_headers("admin"),
        json={"username": name, "password": "probe_pw1", "role_id": 3},
    )
    assert create.json()["code"] == 0
    uid = create.json()["data"]["id"]
    try:
        codes = []
        for _ in range(6):
            resp = _login(client, name, "bad-password")
            codes.append(resp.json()["code"])
        assert codes[-1] == 429, f"expected lockout 429 on 6th attempt, got {codes[-1]}"
    finally:
        client.delete(f"/system/users/{uid}", headers=auth_headers("admin"))


def test_a4_expired_token_401(client):
    resp = client.get("/auth/me", headers={"Authorization": "Bearer invalid.expired.token"})
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_a5_logout_blacklist(client, auth_headers, creds):
    # Use a fresh token so the shared session token survives this test.
    data = _fresh_admin(client, creds)
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/auth/logout", headers=headers)
    assert resp.status_code == 200 and resp.json()["code"] == 0
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 401
    assert me.json()["code"] == 401


def test_a6_refresh_rotation(client, creds):
    # Fresh login: previous logins (a5) supersede older refresh tokens
    # (single-active-session semantics), so never reuse the session fixture token.
    data = _fresh_admin(client, creds)
    r = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200 and r.json()["code"] == 0
    d = r.json()["data"]
    assert d["access_token"]
    assert d["refresh_token"] != data["refresh_token"]


def test_a6b_new_login_invalidates_old_refresh(client, creds):
    # Single-active-session: a new login revokes the previous refresh token.
    data1 = _fresh_admin(client, creds)
    _fresh_admin(client, creds)
    r = client.post("/auth/refresh", json={"refresh_token": data1["refresh_token"]})
    assert r.status_code == 401
    assert r.json()["code"] == 401


def test_a7_refresh_replay_401(client, creds):
    data = _fresh_admin(client, creds)
    rt = data["refresh_token"]
    r1 = client.post("/auth/refresh", json={"refresh_token": rt})
    assert r1.status_code == 200 and r1.json()["code"] == 0
    r2 = client.post("/auth/refresh", json={"refresh_token": rt})
    assert r2.json()["code"] == 401


def test_a8_change_password_roundtrip(client, auth_headers, creds):
    user, pwd = creds["admin"]
    r = client.put(
        "/auth/password",
        headers=auth_headers("admin"),
        json={"old_password": pwd, "new_password": "admin_new_pw_1"},
    )
    assert r.status_code == 200 and r.json()["code"] == 0
    try:
        assert _login(client, user, "admin_new_pw_1").json()["code"] == 0
        assert _login(client, user, pwd).json()["code"] == 401
    finally:
        client.put(
            "/auth/password",
            headers=auth_headers("admin"),
            json={"old_password": "admin_new_pw_1", "new_password": pwd},
        )


def test_a9_change_password_wrong_old(client, auth_headers):
    r = client.put(
        "/auth/password",
        headers=auth_headers("admin"),
        json={"old_password": "not-the-old", "new_password": "whatever123"},
    )
    body = r.json()
    assert body["code"] in (400, 401)


def test_a11_me_full_payload(client, tokens, auth_headers):
    resp = client.get("/auth/me", headers=auth_headers("admin"))
    assert resp.status_code == 200 and resp.json()["code"] == 0
    data = resp.json()["data"]
    assert set(data) >= {"id", "username", "real_name", "roles", "permissions", "visible_group_ids", "is_admin"}


def test_a11b_me_no_token_401(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == 401


def test_a12_no_credentials_in_audit(client, creds, auth_headers):
    user, pwd = creds["admin"]
    _login(client, user, pwd)
    audit = client.get(
        "/system/audit-logs", headers=auth_headers("admin"), params={"size": 100}
    )
    assert audit.status_code == 200 and audit.json()["code"] == 0
    for row in audit.json()["data"]["list"]:
        if row["path"].endswith("/auth/login") or row["path"].endswith("/auth/refresh"):
            params = row.get("params") or {}
            assert "password" not in str(params).lower(), row["path"]
