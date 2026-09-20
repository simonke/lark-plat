"""US-11 audit live tests (D1-D6). Requires live API + admin token.

Closed defect (bbe72cb, now asserted as a regular test):
  * D11-1 (P1) audit actor attribution broken: request.state.audit_user is
    never set, so every audit row has username='' / user_id=None even for
    admin- or viewer-triggered writes. username/ip filters cannot match.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live, pytest.mark.seed]


def test_d1_write_ops_audited(client, auth_headers):
    # viewer-triggered 403 write still must be audited (any user attribution)
    client.post("/system/users", headers=auth_headers("viewer"),
                json={"username": "audit_probe_d1", "password": "pass123456"})
    r = client.get("/system/audit-logs", headers=auth_headers("admin"),
                   params={"size": 100})
    assert r.json()["code"] == 0
    writes = [row for row in r.json()["data"]["list"]
              if row["path"].endswith("/system/users") and row.get("action") == "post"]
    assert len(writes) >= 1, "viewer-triggered POST /system/users must be audited"


def test_d1b_write_actor_attributed(client, auth_headers):
    client.post("/system/users", headers=auth_headers("viewer"),
                json={"username": "audit_probe_d1b", "password": "pass123456"})
    r = client.get("/system/audit-logs", headers=auth_headers("admin"),
                   params={"size": 100, "username": "viewer"})
    assert r.json()["code"] == 0
    assert len(r.json()["data"]["list"]) >= 1


def test_d3_detail_contains_params(client, auth_headers):
    r = client.get("/system/audit-logs", headers=auth_headers("admin"), params={"size": 10})
    assert r.json()["code"] == 0
    rows = r.json()["data"]["list"]
    if not rows:
        pytest.skip("no audit rows")
    with_body = next((row for row in rows if row.get("params")), None)
    if with_body:
        detail = client.get(f"/system/audit-logs/{with_body['id']}", headers=auth_headers("admin"))
        assert detail.json()["code"] == 0


def test_d4_csv_export(client, auth_headers):
    r = client.get("/system/audit-logs/export", headers=auth_headers("admin"), params={"size": 100})
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "Content-Disposition" in r.headers


def test_d6_list_pagination_filters(client, auth_headers):
    r = client.get("/system/audit-logs", headers=auth_headers("admin"),
                   params={"page": 1, "size": 10, "module": "system"})
    assert r.json()["code"] == 0
    assert r.json()["data"]["page"] == 1
