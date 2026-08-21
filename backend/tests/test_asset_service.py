"""Stage-2 asset module contract tests (api-design v2.1 §4 / frontend api/assets.ts).

Runs WITHOUT a database: repositories are faked at the service boundary, the
same style as test_repository_contract.py. Locks the 联调 baseline:
  - HostOut carries group_name/sensitivity_level/updated_at and tags as list[str]
  - credential rows expose host_hostname + created_at + secret_mask
  - /assets/options returns {groups, hostnames, envs}
  - data permission default-deny for non-admin (empty visible groups)
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError
from app.schemas.asset import HostOut
from app.services import asset_service


# ---------------------------------------------------------------- helpers


def make_user(is_admin=True, visible=None):
    return SimpleNamespace(
        id=1, username="admin" if is_admin else "operator",
        is_admin=is_admin, visible_group_ids=visible if visible is not None else [1, 2],
    )


def make_host(**over):
    base = dict(
        id=10, hostname="web-01", ip="10.0.0.1", os_type="linux", os_version="Ubuntu 22.04",
        group_id=1, env="prod", tags=["web"], sensitivity_level="normal", status="offline",
        connector="agent", agent_id=None, agent_version="", last_heartbeat_at=None,
        remark="", created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    base.update(over)
    return SimpleNamespace(**base)


def make_group(gid=1, name="web"):
    return SimpleNamespace(id=gid, parent_id=0, name=name, sort=0, remark="")


class FakeDb:
    def __init__(self, scalars=None):
        self._scalars = scalars or {}
        self.committed = False

    def flush(self):
        pass

    def commit(self):
        self.committed = True

    def delete(self, obj):
        pass

    def scalar(self, stmt):
        return self._scalars.get("scalar", 0)

    def query(self, model):
        return SimpleNamespace(filter=lambda *a, **k: SimpleNamespace(first=lambda: None))


class FakeHostRepo:
    def __init__(self, rows=None, by_ip=None, get=None):
        self._rows = rows or []
        self._by_ip = by_ip
        self._get = get
        self.search_calls = []

    def search(self, filters, page, size):
        self.search_calls.append(filters)
        return list(self._rows), len(self._rows)

    def by_ip(self, ip):
        return self._by_ip

    def get(self, _id):
        return self._get

    def list_all(self):
        return list(self._rows)

    def stats(self, group_ids):
        return {"total": len(self._rows), "online": 0,
                "offline": len(self._rows), "by_env": {}}

    def add(self, obj):
        obj.id = 99
        return obj


class FakeGroupRepo:
    def __init__(self, groups=None, children=0, hosts=0, get=None):
        self._groups = groups or []
        self._children = children
        self._hosts = hosts
        self._get = get

    def all_tree(self):
        return list(self._groups)

    def children_count(self, _id):
        return self._children

    def host_count(self, _id):
        return self._hosts

    def get(self, _id):
        return self._get

    def add(self, obj):
        obj.id = 5
        return obj


class FakeCredRepo:
    def __init__(self, creds=None, by_host=None, get=None):
        self._creds = creds or []
        self._by_host = by_host
        self._get = get
        self.added = []

    def list_all(self):
        return list(self._creds)

    def by_host(self, _id):
        return self._by_host

    def get(self, _id):
        return self._get

    def add(self, obj):
        self.added.append(obj)
        obj.id = 7
        return obj


def patch(monkeypatch, host_repo=None, group_repo=None, cred_repo=None):
    monkeypatch.setattr(asset_service, "HostRepository",
                        lambda db: host_repo or FakeHostRepo())
    monkeypatch.setattr(asset_service, "GroupRepository",
                        lambda db: group_repo or FakeGroupRepo())
    monkeypatch.setattr(asset_service, "CredentialRepository",
                        lambda db: cred_repo or FakeCredRepo())


# ---------------------------------------------------------------- HostOut contract


def test_host_out_normalizes_tags_shapes():
    row = make_host(tags={"label": "web; api"})
    out = HostOut.model_validate(row).model_dump()
    assert out["tags"] == ["web", "api"]
    row2 = make_host(tags=None)
    assert HostOut.model_validate(row2).model_dump()["tags"] == []


def test_host_out_has_contract_fields():
    out = HostOut.model_validate(make_host()).model_dump()
    for field in ("group_name", "sensitivity_level", "updated_at", "status", "connector"):
        assert field in out, f"HostOut must expose {field} (联调契约)"


def test_list_hosts_maps_group_name(monkeypatch):
    patch(monkeypatch,
          host_repo=FakeHostRepo(rows=[make_host()]),
          group_repo=FakeGroupRepo(groups=[make_group(1, "web")]))
    data = asset_service.list_hosts(FakeDb(), make_user(), None, None, None, None,
                                    None, None, None, None, 1, 10)
    assert data["total"] == 1
    assert data["list"][0]["group_name"] == "web"


def test_get_host_includes_group_and_credential_mask(monkeypatch):
    from app.core.security import encrypt_secret

    cred = SimpleNamespace(id=7, type="password", username="root",
                           secret_enc=encrypt_secret("s3cret"), key_enc=None,
                           key_version=1)
    patch(monkeypatch,
          host_repo=FakeHostRepo(get=make_host()),
          group_repo=FakeGroupRepo(groups=[make_group(1, "web")]),
          cred_repo=FakeCredRepo(by_host=cred))
    data = asset_service.get_host(FakeDb(), make_user(), 10)
    assert data["group_name"] == "web"
    assert data["sensitivity_level"] == "normal"
    assert "updated_at" in data
    assert data["credential"]["secret_mask"] != "s3cret"
    assert data["credential"]["secret_mask"]


# ---------------------------------------------------------------- data permission


def test_non_admin_default_deny_empty_visible_groups(monkeypatch):
    repo = FakeHostRepo(rows=[make_host()])
    patch(monkeypatch, host_repo=repo, group_repo=FakeGroupRepo())
    asset_service.list_hosts(FakeDb(), make_user(is_admin=False, visible=[]),
                             None, None, None, None, None, None, None, None, 1, 10)
    assert repo.search_calls[0]["group_ids"] == [], "empty visible groups must default-deny"


def test_non_admin_group_filter_intersects_visible(monkeypatch):
    repo = FakeHostRepo()
    patch(monkeypatch, host_repo=repo, group_repo=FakeGroupRepo())
    asset_service.list_hosts(FakeDb(), make_user(is_admin=False, visible=[1]),
                             None, None, None, 2, None, None, None, None, 1, 10)
    assert repo.search_calls[0]["group_ids"] == [1]


def test_get_host_forbidden_across_groups(monkeypatch):
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host(group_id=3)),
          group_repo=FakeGroupRepo())
    with pytest.raises(ForbiddenError):
        asset_service.get_host(FakeDb(), make_user(is_admin=False, visible=[1]), 10)


# ---------------------------------------------------------------- host CRUD


def test_create_host_rejects_duplicate_ip(monkeypatch):
    patch(monkeypatch, host_repo=FakeHostRepo(by_ip=make_host(id=11)))
    from app.schemas.asset import HostCreate

    with pytest.raises(ConflictError):
        asset_service.create_host(FakeDb(), make_user(),
                                  HostCreate(hostname="h", ip="10.0.0.1"))


def test_create_host_denied_out_of_visible_group(monkeypatch):
    from app.schemas.asset import HostCreate

    patch(monkeypatch, host_repo=FakeHostRepo())
    with pytest.raises(ForbiddenError):
        asset_service.create_host(FakeDb(), make_user(is_admin=False, visible=[1]),
                                  HostCreate(hostname="h", ip="10.0.0.9", group_id=3))


def test_update_host_applies_sensitivity_and_checks_ip(monkeypatch):
    from app.schemas.asset import HostUpdate

    host = make_host()
    patch(monkeypatch, host_repo=FakeHostRepo(get=host))
    asset_service.update_host(FakeDb(), make_user(), 10,
                              HostUpdate(sensitivity_level="sensitive"))
    assert host.sensitivity_level == "sensitive"

    patch(monkeypatch, host_repo=FakeHostRepo(get=host, by_ip=make_host(id=99)))
    with pytest.raises(ConflictError):
        asset_service.update_host(FakeDb(), make_user(), 10, HostUpdate(ip="10.0.0.2"))


def test_delete_host_conflict_when_referenced(monkeypatch):
    from sqlalchemy import select

    db = FakeDb(scalars={"scalar": 1})
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()))
    with pytest.raises(ConflictError):
        asset_service.delete_host(db, make_user(), 10)


# ---------------------------------------------------------------- import/export


def test_import_parses_tags_and_sensitivity(monkeypatch):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["hostname", "ip", "os_type", "env", "group", "tags",
                     "sensitivity_level", "connector"])
    writer.writerow(["db-01", "10.0.0.5", "linux", "prod", "web", "db;master", "sensitive", "ssh"])
    added = []
    repo = FakeHostRepo()
    monkeypatch.setattr(asset_service, "HostRepository", lambda db: repo)

    real_add = repo.add

    def spy_add(obj):
        added.append(obj)
        return real_add(obj)

    repo.add = spy_add
    result = asset_service.import_hosts(FakeDb(), make_user(), buf.getvalue().encode("utf-8"))
    assert result["success"] == 1 and result["failed"] == []
    assert added[0].tags == ["db", "master"]
    assert added[0].sensitivity_level == "sensitive"


def test_import_reports_missing_required_fields(monkeypatch):
    patch(monkeypatch, host_repo=FakeHostRepo())
    result = asset_service.import_hosts(FakeDb(), make_user(), b"ip\n10.0.0.1\n")
    assert result["success"] == 0
    assert result["failed"][0]["error"] == "ip and hostname required"


# ---------------------------------------------------------------- credentials


def test_credential_list_contract_fields(monkeypatch):
    cred = SimpleNamespace(id=7, host_id=10, type="password", username="root",
                           secret_enc="enc:xxx", key_enc=None, key_version=1,
                           created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                           updated_at=datetime(2026, 8, 20, tzinfo=timezone.utc))
    patch(monkeypatch,
          host_repo=FakeHostRepo(rows=[make_host()]),
          cred_repo=FakeCredRepo(creds=[cred]))
    rows = asset_service.list_credentials(FakeDb(), make_user())
    row = rows[0]
    assert row["host_hostname"] == "web-01"
    assert row["created_at"] is not None
    assert row["secret_mask"] and row["secret_mask"] != "enc:xxx"


def test_credential_list_filters_invisible_hosts(monkeypatch):
    cred = SimpleNamespace(id=8, host_id=30, type="password", username="root",
                           secret_enc="enc:x", key_enc=None, key_version=1,
                           created_at=None, updated_at=None)
    patch(monkeypatch,
          host_repo=FakeHostRepo(rows=[make_host(id=30, group_id=3)]),
          cred_repo=FakeCredRepo(creds=[cred]))
    rows = asset_service.list_credentials(FakeDb(), make_user(is_admin=False, visible=[1]))
    assert rows == []


def test_create_credential_validation(monkeypatch):
    from app.schemas.asset import CredentialCreate

    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo())
    with pytest.raises(BadRequestError):
        asset_service.create_credential(FakeDb(), make_user(),
                                        CredentialCreate(host_id=10, type="password", username="root"))
    with pytest.raises(BadRequestError):
        asset_service.create_credential(FakeDb(), make_user(),
                                        CredentialCreate(host_id=10, type="key", username="root"))
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()),
          cred_repo=FakeCredRepo(by_host=SimpleNamespace(id=7)))
    with pytest.raises(ConflictError):
        asset_service.create_credential(FakeDb(), make_user(),
                                        CredentialCreate(host_id=10, type="password",
                                                         username="root", secret="x"))


def test_create_credential_encrypts_secret(monkeypatch):
    from app.core.security import decrypt_secret

    from app.schemas.asset import CredentialCreate

    repo = FakeCredRepo()
    patch(monkeypatch, host_repo=FakeHostRepo(get=make_host()), cred_repo=repo)
    asset_service.create_credential(FakeDb(), make_user(),
                                    CredentialCreate(host_id=10, type="password",
                                                     username="root", secret="s3cret"))
    stored = repo.added[0]
    assert stored.secret_enc != "s3cret"
    assert decrypt_secret(stored.secret_enc) == "s3cret"


# ---------------------------------------------------------------- options / stats / groups


def test_options_contract_shape(monkeypatch):
    patch(monkeypatch, host_repo=FakeHostRepo(rows=[make_host()]),
          group_repo=FakeGroupRepo(groups=[make_group(1, "web")]))
    data = asset_service.options(FakeDb(), make_user())
    assert set(data) == {"groups", "hostnames", "envs"}, "契约：分组树+主机名+环境枚举"
    assert data["hostnames"] == ["web-01"]
    assert data["envs"] == ["dev", "test", "prod"]


def test_group_tree_filters_by_visibility(monkeypatch):
    patch(monkeypatch, group_repo=FakeGroupRepo(groups=[make_group(1, "a"), make_group(2, "b")]))
    tree = asset_service.group_tree(FakeDb(), make_user(is_admin=False, visible=[1]))
    assert [g["name"] for g in tree] == ["a"]


def test_group_tree_nests_children(monkeypatch):
    child = SimpleNamespace(id=2, parent_id=1, name="child", sort=0, remark="")
    patch(monkeypatch, group_repo=FakeGroupRepo(groups=[make_group(1, "root"), child]))
    tree = asset_service.group_tree(FakeDb(), make_user())
    assert tree[0]["name"] == "root"
    assert tree[0]["children"][0]["name"] == "child"


def test_delete_group_guards(monkeypatch):
    patch(monkeypatch, group_repo=FakeGroupRepo(children=1, get=make_group()))
    with pytest.raises(ConflictError):
        asset_service.delete_group(FakeDb(), 1)
    patch(monkeypatch, group_repo=FakeGroupRepo(hosts=1, get=make_group()))
    with pytest.raises(ConflictError):
        asset_service.delete_group(FakeDb(), 1)


def test_create_group_requires_existing_parent(monkeypatch):
    from app.schemas.asset import GroupCreate

    patch(monkeypatch, group_repo=FakeGroupRepo(get=None))
    with pytest.raises(BadRequestError):
        asset_service.create_group(FakeDb(), GroupCreate(parent_id=9, name="x"))


# ---------------------------------------------------------------- connectivity


def test_connectivity_agent_heartbeat_fresh(monkeypatch):
    host = make_host(last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=10))
    patch(monkeypatch, host_repo=FakeHostRepo(get=host))
    result = asset_service.connectivity_check(FakeDb(), make_user(), 10)
    assert result["ok"] is True
    assert host.status == "online"


def test_connectivity_stale_heartbeat_offline(monkeypatch):
    host = make_host(last_heartbeat_at=datetime.now(timezone.utc) - timedelta(seconds=600))
    patch(monkeypatch, host_repo=FakeHostRepo(get=host))
    result = asset_service.connectivity_check(FakeDb(), make_user(), 10)
    assert result["ok"] is False
    assert host.status == "offline"


def test_connectivity_no_agent(monkeypatch):
    host = make_host(last_heartbeat_at=None)
    patch(monkeypatch, host_repo=FakeHostRepo(get=host))
    result = asset_service.connectivity_check(FakeDb(), make_user(), 10)
    assert result["ok"] is False and result["detail"] == "no agent"
