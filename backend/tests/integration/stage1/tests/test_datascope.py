"""US-03 data scope (role_host_group) live tests (C1-C6). Requires live API.

Closed defects (bbe72cb, now asserted as regular tests):
  * D3-1 (P1) host-list default-deny leak: unbound viewer sees ALL hosts because
    HostRepository.search treats empty group_ids as "no filter" instead of
    default-deny 0 rows (asset_repo.search `if filters.get("group_ids")`).
  * D3-2 (P1) group tree not data-scoped: /assets/groups/tree ignores the
    user, operator sees groupB too (asset_service.group_tree(db) drops user).
  * D3-3 (P1) host tag filter 500: HostRepository.search casted
    Host.tags as text ("text" cast), which PostgreSQL rejects; fixed to String.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.live, pytest.mark.seed]


def _admin_host_ids_by_name(client, auth_headers) -> dict:
    r = client.get("/assets/hosts", headers=auth_headers("admin"), params={"size": 100})
    assert r.json()["code"] == 0
    return {h["hostname"]: h["id"] for h in r.json()["data"]["list"]}


@pytest.fixture(scope="module")
def host_ids(client, auth_headers) -> dict:
    ids = _admin_host_ids_by_name(client, auth_headers)
    assert {"hostA1", "hostA2", "hostB1"} <= set(ids), f"seed hosts missing: {sorted(ids)}"
    return ids


def _admin_all_hosts(client, auth_headers) -> dict:
    r = client.get("/assets/hosts", headers=auth_headers("admin"), params={"size": 100})
    assert r.json()["code"] == 0
    return {h["hostname"]: h.get("group_name") for h in r.json()["data"]["list"]}


@pytest.fixture(scope="module")
def operator_scope(client, auth_headers) -> dict:
    """Operator's data scope derived from live state (robust to shared-DB seeds).

    The live DB is shared, so groupA accumulates hosts from other suites; asserting
    a hardcoded count is brittle. The frozen US-03 invariant is "operator sees
    exactly its bound group(s), and nothing outside" — we derive the expected
    membership from admin's own view filtered by the operator's group tree.
    """
    tree = client.get("/assets/groups/tree", headers=auth_headers("operator"))
    assert tree.json()["code"] == 0
    group_ids = [g["id"] for g in tree.json()["data"]]
    expected: set = set()
    for gid in group_ids:
        r = client.get("/assets/hosts", headers=auth_headers("admin"),
                       params={"size": 100, "group_id": gid})
        assert r.json()["code"] == 0
        expected |= {h["hostname"] for h in r.json()["data"]["list"]}
    all_hosts = set(_admin_all_hosts(client, auth_headers))
    return {
        "group_ids": group_ids,
        "expected": expected,
        "outside": all_hosts - expected,
    }


def test_c1_admin_sees_all_hosts(client, auth_headers):
    r = client.get("/assets/hosts", headers=auth_headers("admin"), params={"size": 100})
    assert r.json()["code"] == 0
    total = r.json()["data"]["total"]
    assert total >= 3, f"admin should see group A+B hosts, got {total}"


def test_c2_operator_sees_only_group_a(client, auth_headers, operator_scope):
    r = client.get("/assets/hosts", headers=auth_headers("operator"), params={"size": 100})
    assert r.json()["code"] == 0
    hostnames = {h["hostname"] for h in r.json()["data"]["list"]}
    assert {"hostA1", "hostA2"} <= operator_scope["expected"], "seed group-A hosts missing"
    assert hostnames == operator_scope["expected"], (
        f"scope mismatch: leaked={sorted(hostnames - operator_scope['expected'])}, "
        f"hidden={sorted(operator_scope['expected'] - hostnames)}"
    )
    assert operator_scope["outside"], "no out-of-scope host exists; isolation untestable"
    assert not (hostnames & operator_scope["outside"]), (
        f"cross-group leak: {sorted(hostnames & operator_scope['outside'])}"
    )
    assert "hostB1" not in hostnames


def test_c3_viewer_unbound_default_deny(client, auth_headers):
    r = client.get("/assets/hosts", headers=auth_headers("viewer"), params={"size": 100})
    assert r.json()["code"] == 0
    assert r.json()["data"]["total"] == 0, "unbound viewer must see 0 hosts (default deny)"


def test_c4_cross_group_read_rejected(client, auth_headers, host_ids):
    r = client.get(f"/assets/hosts/{host_ids['hostB1']}", headers=auth_headers("operator"))
    assert r.json()["code"] in (403, 404)


def test_c6_group_tree_scoped(client, auth_headers):
    r = client.get("/assets/groups/tree", headers=auth_headers("operator"))
    assert r.json()["code"] == 0
    names = {g["name"] for g in r.json()["data"]}
    assert names == {"groupA"}, f"operator must see only groupA, got {sorted(names)}"


def test_c7_host_tag_filter_no_500(client, auth_headers):
    r = client.get("/assets/hosts", headers=auth_headers("admin"),
                   params={"size": 10, "tag": "x"})
    assert r.json()["code"] == 0, "tag filter must not 500 (D3-3 Host.tags cast String)"
