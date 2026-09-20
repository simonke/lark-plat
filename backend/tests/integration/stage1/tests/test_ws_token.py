"""WS-token ownership checks (E1-E5, P1-② regression + IDOR). Requires exec task seeds.

Live seed: run `tools/stage1_seed.py --ensure` first. It creates the
operator-owned task `it-ws-seed` (task_no IT-WS-SEED-001) that E1 needs; the
former "no exec tasks seeded" hard skip is gone (架构 seq2140 item4).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live, pytest.mark.seed]

_SEED_NAME = "it-ws-seed"


def _find_seed_task(client, auth_headers) -> dict:
    r = client.get("/exec/tasks", headers=auth_headers("operator"), params={"name": _SEED_NAME, "size": 10})
    assert r.status_code == 200 and r.json()["code"] == 0, r.text
    rows = r.json()["data"]["list"]
    if not rows:
        pytest.fail(
            "no operator-owned exec task seeded — run "
            "tests/integration/stage1/tools/stage1_seed.py --ensure"
        )
    return rows[0]


def test_e3_viewer_lacks_ws_token_ownership(client, auth_headers):
    # viewer has exec:task:log (read-only role), so the perm gate passes and the
    # lookup proceeds; unknown task -> 404. Ownership rejection (403) for a task
    # owned by someone else is covered by e2.
    r = client.get("/exec/tasks/99999/hosts/99999/ws-token", headers=auth_headers("viewer"))
    assert r.json()["code"] in (403, 404)


def test_e4_unknown_task_404(client, auth_headers):
    r = client.get("/exec/tasks/999999/hosts/999999/ws-token", headers=auth_headers("admin"))
    assert r.json()["code"] in (404,)


def test_e1_owner_gets_token(client, auth_headers):
    task = _find_seed_task(client, auth_headers)
    detail = client.get(f"/exec/tasks/{task['id']}", headers=auth_headers("operator"))
    assert detail.json()["code"] == 0, detail.text
    hosts = detail.json()["data"].get("hosts") or []
    assert hosts, "seeded task has no exec_task_host"
    th_id = hosts[0]["id"] if isinstance(hosts[0], dict) else hosts[0]
    r = client.get(
        f"/exec/tasks/{task['id']}/hosts/{th_id}/ws-token", headers=auth_headers("operator")
    )
    assert r.json()["code"] == 0, r.text
    assert r.json()["data"]["token"]


def test_e2_non_owner_rejected(client, auth_headers):
    """IDOR guard: operator must not mint a ws-token for a task it does not own."""
    mine = _find_seed_task(client, auth_headers)
    admin_tasks = client.get(
        "/exec/tasks", headers=auth_headers("admin"), params={"size": 100}
    ).json()["data"]["list"]
    foreign = next((t for t in admin_tasks if t["created_by"] != mine["created_by"]), None)
    if foreign is None:
        pytest.skip("no foreign-owned task available to assert IDOR rejection")
    r = client.get(
        f"/exec/tasks/{foreign['id']}/hosts/1/ws-token", headers=auth_headers("operator")
    )
    assert r.json()["code"] in (403, 404), r.text
