"""AuthService unit tests (stage-1 US-01/02/03).

Pattern: service depends on repository interfaces + redis helpers; tests
inject fakes via monkeypatch (no DB / no Redis required).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import UnauthorizedError
from app.services import auth_service

FAKE_HASH = "$2b$12$abcdefghijklmnopqrstuvwxyz1234567890ABCD"


def _user(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        username="alice",
        real_name="Alice",
        status=1,
        deleted=0,
        is_admin=0,
        password_hash=FAKE_HASH,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def user_repo_fake(monkeypatch):
    repo = SimpleNamespace()
    auth_service.UserRepository = lambda db: repo
    return repo


@pytest.fixture
def empty_role_ids(monkeypatch):
    monkeypatch.setattr(auth_service, "_role_ids", lambda db, uid: [])


@pytest.fixture
def redis_ok(monkeypatch):
    for name in (
        "record_login_failure",
        "clear_login_failures",
        "blacklist_access",
        "revoke_refresh",
        "store_refresh",
        "validate_refresh",
    ):
        monkeypatch.setattr(auth_service, name, lambda *a, **k: None)
    monkeypatch.setattr(auth_service, "validate_refresh", lambda *a, **k: True)


@pytest.fixture
def tokens_ok(monkeypatch):
    monkeypatch.setattr(auth_service, "create_access_token", lambda uid: "access-token")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda uid: "refresh-token")
    monkeypatch.setattr(auth_service, "decode_token", lambda tok, expected=None: {"jti": "j1", "sub": "1"})


def _fake_db(commit=False):
    db = SimpleNamespace()
    if commit:
        db.commit = lambda: None
    return db


# ---------------------------------------------------------------- contract shape


def test_login_user_is_basic_contract_shape(user_repo_fake, empty_role_ids, redis_ok, tokens_ok, monkeypatch):
    """Contract v2.1 §2: /auth/login returns user{id,username,real_name,roles} only.

    Full profile (permissions/visible_group_ids/is_admin) is served by /auth/me.
    """
    monkeypatch.setattr(auth_service, "verify_password", lambda *a, **k: True)
    user_repo_fake.by_username = lambda u: _user()
    user_repo_fake.get = lambda i: _user()
    result = auth_service.login(_fake_db(commit=True), "alice", "pw")
    assert result["access_token"] == "access-token"
    assert result["refresh_token"] == "refresh-token"
    assert result["token_type"] == "bearer"
    user = result["user"]
    assert set(user) == {"id", "username", "real_name", "roles"}
    assert user["id"] == 1
    assert user["username"] == "alice"
    assert user["real_name"] == "Alice"


# ---------------------------------------------------------------- login guards


def test_login_rejects_unknown_user(user_repo_fake, empty_role_ids, redis_ok, tokens_ok):
    user_repo_fake.by_username = lambda u: None
    with pytest.raises(UnauthorizedError):
        auth_service.login(_fake_db(), "nobody", "pw")


def test_login_rejects_wrong_password_and_records_failure(user_repo_fake, monkeypatch):
    user_repo_fake.by_username = lambda u: _user()
    recorded = []
    monkeypatch.setattr(auth_service, "record_login_failure", lambda u: recorded.append(u))
    monkeypatch.setattr(auth_service, "verify_password", lambda *a, **k: False)
    with pytest.raises(UnauthorizedError):
        auth_service.login(_fake_db(), "alice", "bad")
    assert recorded == ["alice"]


def test_login_rejects_disabled_user(user_repo_fake, empty_role_ids, redis_ok, tokens_ok):
    user_repo_fake.by_username = lambda u: _user(status=0)
    with pytest.raises(UnauthorizedError):
        auth_service.login(_fake_db(), "alice", "pw")


def test_login_success_clears_failures_and_updates_last_login(user_repo_fake, empty_role_ids, redis_ok, tokens_ok, monkeypatch):
    cleared = []
    auth_service.clear_login_failures = lambda u: cleared.append(u)
    monkeypatch.setattr(auth_service, "verify_password", lambda *a, **k: True)
    db = _fake_db(commit=True)
    user = _user()
    user_repo_fake.by_username = lambda u: user
    user_repo_fake.get = lambda i: user
    auth_service.login(db, "alice", "pw")
    assert cleared == ["alice"]
    assert user.last_login_at is not None


# ---------------------------------------------------------------- refresh / logout


def test_refresh_rotates_tokens(monkeypatch, empty_role_ids):
    db = _fake_db()
    user_repo = SimpleNamespace(get=lambda i: _user())
    monkeypatch.setattr(auth_service, "UserRepository", lambda db: user_repo)
    stored = []
    monkeypatch.setattr(auth_service, "store_refresh", lambda uid, jti: stored.append(jti))
    monkeypatch.setattr(auth_service, "validate_refresh", lambda uid, jti: True)
    monkeypatch.setattr(auth_service, "create_access_token", lambda uid: "access-2")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda uid: "refresh-2")
    monkeypatch.setattr(auth_service, "decode_token", lambda tok, expected=None: {"jti": "j2", "sub": "1"})
    result = auth_service.refresh_tokens(db, "refresh-old")
    assert result["access_token"] == "access-2"
    assert result["refresh_token"] == "refresh-2"
    assert stored == ["j2"]


def test_refresh_rejects_reused_token(monkeypatch):
    db = _fake_db()
    monkeypatch.setattr(auth_service, "UserRepository", lambda db: SimpleNamespace(get=lambda i: _user()))
    monkeypatch.setattr(auth_service, "decode_token", lambda tok, expected=None: {"jti": "j-old", "sub": "1"})
    monkeypatch.setattr(auth_service, "validate_refresh", lambda uid, jti: False)
    with pytest.raises(UnauthorizedError):
        auth_service.refresh_tokens(db, "refresh-old")


def test_logout_blacklists_access_jti(monkeypatch):
    calls = {}
    monkeypatch.setattr(auth_service, "decode_token", lambda tok, expected=None: {"jti": "j-access", "sub": "1"})
    monkeypatch.setattr(auth_service, "blacklist_access", lambda jti: calls.update(bl=jti))
    monkeypatch.setattr(auth_service, "revoke_refresh", lambda uid: calls.update(revoke=uid))
    auth_service.logout(_fake_db(), "some-token")
    assert calls == {"bl": "j-access", "revoke": 1}


# ---------------------------------------------------------------- me


def test_me_returns_full_profile(monkeypatch):
    user = _user(is_admin=1)
    monkeypatch.setattr(auth_service, "UserRepository", lambda db: SimpleNamespace(get=lambda i: user))
    monkeypatch.setattr(auth_service, "_role_ids", lambda db, uid: [1, 2])

    roles = [SimpleNamespace(id=1, code="admin", name="Admin")]
    perms = ["system:user:list", "system:audit:list"]
    visible = [10, 20]

    class RoleRepo:
        def get(self, rid):
            return roles[0] if rid == 1 else None

        def visible_group_ids(self, rids):
            return visible

    class PermRepo:
        def codes_by_user(self, uid):
            return perms

    monkeypatch.setattr(auth_service, "RoleRepository", lambda db: RoleRepo())
    monkeypatch.setattr(auth_service, "PermissionRepository", lambda db: PermRepo())

    me = auth_service.me(_fake_db(), 1)
    assert me["permissions"] == perms
    assert me["visible_group_ids"] == visible
    assert me["is_admin"] is True
    assert me["roles"][0]["code"] == "admin"
