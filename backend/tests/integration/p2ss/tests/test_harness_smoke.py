"""Harness smoke test (pre-P2-SS): proves the offline app boots, RBAC and data
permission are enforced through the real HTTP stack, and persistence works.

Uses existing asset endpoints so it runs against the current tree (before the
P2-SS endpoints exist); it is scaffolding, not the P2-SS deliverable.
"""

from __future__ import annotations


def test_get_host_ok_as_admin(app_client):
    client, set_user, seed_host = app_client
    set_user(admin=True)
    hid = seed_host(1)
    resp = client.get(f"/api/v1/assets/hosts/{hid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["id"] == hid


def test_get_host_ok_with_perm_and_visible_group(app_client):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:list"})
    hid = seed_host(1)
    resp = client.get(f"/api/v1/assets/hosts/{hid}")
    assert resp.status_code == 200, resp.text


def test_get_host_403_without_perm(app_client):
    client, set_user, seed_host = app_client
    set_user(perms=set())
    hid = seed_host(1)
    resp = client.get(f"/api/v1/assets/hosts/{hid}")
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 403


def test_put_host_requires_edit_and_persists(app_client, session):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1)

    resp = client.put(f"/api/v1/assets/hosts/{hid}", json={"remark": "touched"})
    assert resp.status_code == 200, resp.text

    session.expire_all()
    from app.db.models import Host

    assert session.get(Host, hid).remark == "touched"


def test_put_host_403_without_edit(app_client):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:list"})
    hid = seed_host(1)
    resp = client.put(f"/api/v1/assets/hosts/{hid}", json={"remark": "nope"})
    assert resp.status_code == 403, resp.text
