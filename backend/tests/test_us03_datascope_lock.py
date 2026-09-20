"""US-03 data-isolation contract lock — @单元测试工程师 (offline, no DB / no live).

Scope: the FROZEN US-03 data-permission red line (需求 seq2124 第2点), asserted
purely at the service/repository boundary with fakes — **no shared DB, no live
uvicorn, no seeded rows**. This is the "等价证据/兜底" adopted in 架构 seq2127
(裁决源: @单元测试工程师 seq2126) for the live `test_datascope::c2` red, which
was diagnosed as shared-DB seed accumulation (c6 groupA PASS ⇒ isolation intact),
NOT a logic defect.

This lock does NOT replace the integration seat's primary path (fixture-private
host groups + seed cleanup + live re-run); it is an independent offline
equivalent and must not be used to "judge isolation defective" on live.

Pins (mirror c2 "operator sees only its group" and c6 "group tree only groupA"):
  D1  asset_service._visible_group_filter: non-admin injects visible_group_ids as
      an explicit `group_ids` filter; empty visible ⇒ explicit `group_ids=[]`
      (default-deny, US-03); explicit request is intersected with visible; admin
      is never narrowed.
  D2  asset_service._host_visible: admin ⇒ all; non-admin ⇒ group_id ∈ visible;
      empty visible ⇒ deny.
  D3  asset_service.get_host: out-of-scope host ⇒ ForbiddenError; in-scope ⇒ ok.
  D4  asset_service.group_tree: non-admin ⇒ only visible groups (c6 analog);
      admin ⇒ all.
  D5  asset_service.create_host: writing into a non-visible group ⇒ ForbiddenError.
  D6  CurrentUser.require_group: non-visible ⇒ ForbiddenError; admin bypass.
  D7  RoleRepository.visible_group_ids([]): no roles ⇒ no groups (deny source).

Run from the backend checkout (external cwd=backend, backend venv):
    pytest <this file> -p no:cacheprovider -q
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


# ── import guards (clean RED instead of collection errors) ───────────────────

def _try(mod: str, *names: str):
    try:
        m = importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return (None, exc) if not names else tuple([None] * len(names) + [exc])
    got = tuple(getattr(m, n, None) for n in names)
    return got if names else m


asset_service = _try("app.services.asset_service")
sch = _try("app.schemas.asset")
deps = _try("app.api.deps")
repos = _try("app.repositories")
exceptions = _try("app.core.exceptions")


def _need(*objs):
    for o in objs:
        if isinstance(o, Exception) or o is None:
            pytest.fail(f"US-03 lock: module unavailable: {o!r}")


# ── helpers ──────────────────────────────────────────────────────────────────

def _user(is_admin: bool, visible=()):
    return SimpleNamespace(
        id=1, username="admin" if is_admin else "operator",
        is_admin=is_admin, visible_group_ids=list(visible),
    )


def _host(gid: int | None):
    return SimpleNamespace(group_id=gid)


def _group(gid: int, name: str, parent_id: int = 0):
    return SimpleNamespace(id=gid, parent_id=parent_id, name=name, sort=0, remark="")


def _full_host(gid: int, hid: int = 10, hostname: str = "web-01", ip: str = "10.0.0.1"):
    return SimpleNamespace(
        id=hid, hostname=hostname, ip=ip, os_type="linux", os_version="",
        group_id=gid, env="prod", tags=["web"], sensitivity_level="normal",
        status="offline", connector="agent", agent_id=None, agent_version="",
        last_heartbeat_at=None, remark="",
        created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
    )


def _install_fakes(monkeypatch, hosts=None, groups=None, creds=None):
    """Fake the repository classes at the asset_service boundary (no Session)."""
    hosts = hosts or {}

    class FakeHostRepo:
        def __init__(self, db):
            pass

        def get(self, hid):
            return hosts.get(hid)

        def by_ip(self, ip):
            return None

        def add(self, obj):
            return obj

    class FakeGroupRepo:
        def __init__(self, db):
            pass

        def all_tree(self):
            return list(groups or [])

    class FakeCredRepo:
        def __init__(self, db):
            pass

        def by_host(self, hid):
            return (creds or {}).get(hid)

    monkeypatch.setattr(asset_service, "HostRepository", FakeHostRepo)
    monkeypatch.setattr(asset_service, "GroupRepository", FakeGroupRepo)
    monkeypatch.setattr(asset_service, "CredentialRepository", FakeCredRepo)


# ── D1: _visible_group_filter ────────────────────────────────────────────────

def test_d1_default_deny_empty_visible_injects_empty_group_ids():
    _need(asset_service)
    f = asset_service._visible_group_filter(_user(False, []), {})
    assert "group_ids" in f, "deny seam must be an explicit (present) group_ids key"
    assert f["group_ids"] == []


def test_d1_non_admin_injects_visible_groups():
    _need(asset_service)
    f = asset_service._visible_group_filter(_user(False, [1, 2]), {})
    assert sorted(f["group_ids"]) == [1, 2]


def test_d1_explicit_request_intersected_with_visible():
    _need(asset_service)
    f = asset_service._visible_group_filter(_user(False, [1]), {"group_ids": [1, 2, 3]})
    assert f["group_ids"] == [1]


def test_d1_admin_not_narrowed():
    _need(asset_service)
    f = asset_service._visible_group_filter(_user(True, []), {})
    assert "group_ids" not in f
    f2 = asset_service._visible_group_filter(_user(True, []), {"group_ids": [1, 2]})
    assert f2["group_ids"] == [1, 2]


# ── D2: _host_visible ────────────────────────────────────────────────────────

def test_d2_host_visible_matrix():
    _need(asset_service)
    assert asset_service._host_visible(_user(True, []), _host(9)) is True
    assert asset_service._host_visible(_user(False, [1]), _host(1)) is True
    assert asset_service._host_visible(_user(False, [1]), _host(2)) is False
    assert asset_service._host_visible(_user(False, []), _host(1)) is False


# ── D3: get_host ─────────────────────────────────────────────────────────────

def test_d3_get_host_denied_out_of_scope(monkeypatch):
    _need(asset_service, exceptions)
    _install_fakes(monkeypatch, hosts={10: _full_host(gid=2)})
    with pytest.raises(exceptions.ForbiddenError):
        asset_service.get_host(None, _user(False, [1]), 10)


def test_d3_get_host_visible_returns_group_name(monkeypatch):
    _need(asset_service)
    _install_fakes(monkeypatch, hosts={10: _full_host(gid=1)}, groups=[_group(1, "A")])
    out = asset_service.get_host(None, _user(False, [1]), 10)
    assert out["group_name"] == "A"


# ── D4: group_tree (c6 analog) ───────────────────────────────────────────────

def test_d4_group_tree_filters_to_visible(monkeypatch):
    _need(asset_service)
    _install_fakes(monkeypatch, groups=[_group(1, "A"), _group(2, "B")])
    roots = asset_service.group_tree(None, _user(False, [1]))
    assert [g["name"] for g in roots] == ["A"]
    roots_admin = asset_service.group_tree(None, _user(True, []))
    assert sorted(g["name"] for g in roots_admin) == ["A", "B"]


# ── D5: create_host ──────────────────────────────────────────────────────────

def test_d5_create_host_denied_out_of_scope():
    _need(asset_service, sch, exceptions)
    data = sch.HostCreate(hostname="h", ip="10.0.0.9", group_id=2)
    with pytest.raises(exceptions.ForbiddenError):
        asset_service.create_host(None, _user(False, [1]), data)


# ── D6: CurrentUser.require_group ────────────────────────────────────────────

def test_d6_current_user_require_group():
    _need(deps, exceptions)
    cu = deps.CurrentUser(user_id=1, username="op", is_admin=False,
                          permissions=[], visible_group_ids=[1])
    cu.require_group(1)  # in scope: no raise
    with pytest.raises(exceptions.ForbiddenError):
        cu.require_group(2)
    admin = deps.CurrentUser(user_id=1, username="admin", is_admin=True,
                             permissions=[], visible_group_ids=[])
    admin.require_group(99)  # admin bypass: no raise


# ── D7: RoleRepository.visible_group_ids ─────────────────────────────────────

def test_d7_role_repo_no_roles_default_deny():
    _need(repos)
    repo = repos.RoleRepository(None)  # session unused for the empty-roles path
    assert repo.visible_group_ids([]) == []
