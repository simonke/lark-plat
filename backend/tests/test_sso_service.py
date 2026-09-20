"""P2-3 identity integration lock tests (providers CRUD, LDAP, OAuth2).

Pattern mirrors test_auth_service: the service depends on repositories + redis
helpers; tests inject fakes via monkeypatch (no DB / no Redis / no network).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.services import auth_service, sso_service

FAKE_ENC = "v1:ZmFrZQ=="


def _provider(**overrides) -> SimpleNamespace:
    base = dict(
        id=1,
        code="okta",
        name="Okta",
        type="oauth2",
        config_enc=FAKE_ENC,
        enabled=1,
        created_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeProviderRepo:
    def __init__(self, providers=None, by_code=None):
        self._providers = list(providers or [])
        self._by_code = by_code
        self.added = []
        self.deleted = []

    def list_all(self):
        return list(self._providers)

    def list_enabled(self):
        return [p for p in self._providers if p.enabled == 1]

    def by_code(self, code):
        if self._by_code is not None:
            return self._by_code
        return next((p for p in self._providers if p.code == code), None)

    def get(self, pid):
        return next((p for p in self._providers if p.id == pid), None)

    def add(self, provider):
        self.added.append(provider)

    def delete(self, provider):
        self.deleted.append(provider)


def _db():
    return SimpleNamespace(commit=lambda: None, flush=lambda: None, delete=lambda o: None, add=lambda o: None)


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.setattr(sso_service, "_feature_enabled", lambda db: True)


@pytest.fixture(autouse=True)
def _plain_config(monkeypatch):
    """Identity config codec so CRUD tests don't depend on the AES key."""
    monkeypatch.setattr(sso_service, "encrypt_secret", lambda s: "enc(" + s + ")")
    monkeypatch.setattr(sso_service, "decrypt_secret", lambda s: s.removeprefix("enc(").removesuffix(")"))


# ---------------------------------------------------------------- login methods / list


def test_login_methods_includes_local_and_enabled_only(monkeypatch):
    repo = _FakeProviderRepo([
        _provider(id=1, code="okta", type="oauth2", enabled=1),
        _provider(id=2, code="corp-ldap", type="ldap", enabled=0),
    ])
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: repo)
    methods = sso_service.login_methods(_db())
    assert methods[0] == {"code": "local", "type": "local", "name": "账号密码"}
    assert {"code": "okta", "type": "oauth2", "name": "Okta"} in methods
    assert all(m["code"] != "corp-ldap" for m in methods)


def test_login_methods_keeps_frozen_brief_keys(monkeypatch):
    """§3: entry shape stays exactly {code,type,name} (no login_path leak)."""
    repo = _FakeProviderRepo([_provider(code="okta")])
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: repo)
    for entry in sso_service.login_methods(_db()):
        assert set(entry) == {"code", "type", "name"}


def test_list_providers_masks_secret_values(monkeypatch):
    provider = _provider(config_enc="enc(" + sso_service.json.dumps(
        {"client_id": "abc", "client_secret": "supersecret", "token_url": "https://idp/token"}
    ) + ")")
    repo = _FakeProviderRepo([provider])
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: repo)
    out = sso_service.list_providers(_db())[0]
    assert set(out) == {"id", "code", "name", "type", "enabled", "config_mask", "created_at"}
    assert out["config_mask"]["client_id"] == "abc"
    assert "supersecret" not in str(out["config_mask"])
    assert out["config_mask"]["client_secret"].endswith("****")


# ---------------------------------------------------------------- slug / create / delete


def test_normalize_code_rejects_bad_chars():
    with pytest.raises(BadRequestError):
        sso_service._normalize_code("Bad Code!", "x")


def test_create_provider_slugs_name_and_rejects_duplicate(monkeypatch):
    repo = _FakeProviderRepo(by_code=None)
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: repo)
    out = sso_service.create_provider(
        _db(), SimpleNamespace(name="Corp LDAP", type="ldap", code=None, config={}, enabled=1)
    )
    assert out["code"] == "corp-ldap"
    assert out["type"] == "ldap"

    repo._by_code = _provider(code="corp-ldap")
    with pytest.raises(BadRequestError):
        sso_service.create_provider(
            _db(), SimpleNamespace(name="dup", type="ldap", code="corp-ldap", config={}, enabled=1)
        )


def test_create_provider_rejects_unknown_type(monkeypatch):
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo())
    with pytest.raises(BadRequestError):
        sso_service.create_provider(
            _db(), SimpleNamespace(name="x", type="saml", code="x", config={}, enabled=1)
        )


def test_delete_provider_missing_raises(monkeypatch):
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo())
    with pytest.raises(NotFoundError):
        sso_service.delete_provider(_db(), 999)


def test_update_provider_keeps_ciphertext_when_secret_masked(monkeypatch):
    provider = _provider(
        code="corp-ldap",
        type="ldap",
        config_enc="enc(" + sso_service.json.dumps({"bind_password": "realpw", "base_dn": "dc=x"}) + ")",
    )
    repo = _FakeProviderRepo([provider])
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: repo)
    sso_service.update_provider(
        _db(), 1, SimpleNamespace(name=None, enabled=None, config={"bind_password": "re****", "base_dn": "dc=y"})
    )
    stored = sso_service._decrypt_config(provider)
    assert stored["bind_password"] == "realpw"  # masked echo must not overwrite
    assert stored["base_dn"] == "dc=y"


# ---------------------------------------------------------------- feature flag


def test_create_provider_blocked_when_feature_disabled(monkeypatch):
    monkeypatch.setattr(sso_service, "_feature_enabled", lambda db: False)
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo())
    with pytest.raises(BadRequestError):
        sso_service.create_provider(
            _db(), SimpleNamespace(name="x", type="ldap", code="x", config={}, enabled=1)
        )


# ---------------------------------------------------------------- LDAP login


def test_ldap_login_without_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([]))
    with pytest.raises(BadRequestError):
        sso_service.ldap_login(_db(), "alice", "pw")


def test_ldap_login_maps_to_existing_user_and_issues_tokens(monkeypatch):
    provider = _provider(id=1, code="corp-ldap", type="ldap")
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([provider]))
    monkeypatch.setattr(sso_service, "_ldap_attributes", lambda p, u, pw: {"uid": "alice", "mail": "a@x"})
    monkeypatch.setattr(sso_service, "_decrypt_config", lambda p: {"map_key": "username"})
    user = SimpleNamespace(id=7, username="alice", auth_source="ldap")
    monkeypatch.setattr(sso_service, "_resolve_external_user", lambda db, p, mv, prof: user)
    monkeypatch.setattr(auth_service, "issue_tokens", lambda db, u: {"access_token": "a", "user": {"id": 7}})
    monkeypatch.setattr(sso_service, "clear_login_failures", lambda u: None)
    result = sso_service.ldap_login(_db(), "alice", "pw")
    assert result["access_token"] == "a"


def test_ldap_login_failure_records_failure_and_raises(monkeypatch):
    provider = _provider(id=1, code="corp-ldap", type="ldap")
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([provider]))

    def _boom(p, u, pw):
        raise UnauthorizedError("bad bind")

    monkeypatch.setattr(sso_service, "_ldap_attributes", _boom)
    recorded = []
    monkeypatch.setattr(sso_service, "record_login_failure", lambda u: recorded.append(u))
    with pytest.raises(UnauthorizedError):
        sso_service.ldap_login(_db(), "alice", "bad")
    assert recorded == ["alice"]


def test_provisioning_requires_opt_in(monkeypatch):
    provider = _provider(id=1, code="corp-ldap", type="ldap")
    monkeypatch.setattr(sso_service, "UserRepository", lambda db: SimpleNamespace(by_username=lambda u: None, by_email=lambda e: None))
    monkeypatch.setattr(sso_service, "_config_rule", lambda db, k, d: False)
    with pytest.raises(UnauthorizedError):
        sso_service._resolve_external_user(_db(), provider, "ghost", {"map_key": "username"})


# ---------------------------------------------------------------- OAuth2


def test_oauth_authorize_url_embeds_state_and_client(monkeypatch):
    provider = _provider(code="okta")
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([provider]))
    monkeypatch.setattr(
        sso_service, "_decrypt_config",
        lambda p: {"authorize_url": "https://idp/auth", "client_id": "cid", "scope": "openid"},
    )
    stored = {}
    monkeypatch.setattr(sso_service, "store_oauth_state", lambda s, payload, ttl: stored.update(state=s, ttl=ttl, payload=payload))
    url = sso_service.oauth_authorize_url(_db(), "okta", "http://localhost:8000/")
    assert url.startswith("https://idp/auth?")
    assert "client_id=cid" in url and "state=" in url and "response_type=code" in url
    assert stored["ttl"] == sso_service.OAUTH_STATE_TTL
    assert stored["payload"]["code"] == "okta"


def test_oauth_callback_rejects_bad_state(monkeypatch):
    provider = _provider(code="okta")
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([provider]))
    monkeypatch.setattr(sso_service, "consume_oauth_state", lambda s: None)
    with pytest.raises(BadRequestError):
        sso_service.oauth_callback(_db(), "okta", "authcode", "replayed")


def test_oauth_callback_maps_user_and_issues_tokens(monkeypatch):
    provider = _provider(code="okta")
    monkeypatch.setattr(sso_service, "AuthProviderRepository", lambda db: _FakeProviderRepo([provider]))
    monkeypatch.setattr(sso_service, "consume_oauth_state", lambda s: {"code": "okta", "redirect_uri": "http://cb"})
    monkeypatch.setattr(
        sso_service, "_decrypt_config",
        lambda p: {"map_key": "email", "userinfo_url": "https://idp/me", "auto_provision": True},
    )
    monkeypatch.setattr(sso_service, "_oauth_exchange", lambda cfg, code, ruri: "tok")
    monkeypatch.setattr(sso_service, "_oauth_profile", lambda cfg, tok: {"email": "a@x", "name": "Alice", "sub": "s1"})
    user = SimpleNamespace(id=5, username="a@x")
    monkeypatch.setattr(sso_service, "_resolve_external_user", lambda db, p, mv, prof: user)
    monkeypatch.setattr(auth_service, "issue_tokens", lambda db, u: {"access_token": "a", "refresh_token": "r", "token_type": "bearer", "user": {"id": 5}})
    monkeypatch.setattr(sso_service, "clear_login_failures", lambda u: None)
    monkeypatch.setattr(sso_service, "_config_rule", lambda db, k, d: None)
    result = sso_service.oauth_callback(_db(), "okta", "authcode", "state1")
    assert result["access_token"] == "a"
    assert result["provider"]["code"] == "okta"
    assert "redirect_after" in result


def test_frontend_callback_url_precedence(monkeypatch):
    monkeypatch.setattr(sso_service, "_config_rule", lambda db, k, d: "https://ops/cb")
    assert sso_service.frontend_callback_url(_db()) == "https://ops/cb"
    assert sso_service.frontend_callback_url(_db(), {"redirect_after": "https://p/cb"}) == "https://p/cb"


# ---------------------------------------------------------------- contract guards


def test_login_userbrief_stays_frozen_with_auth_source_exposed_in_me(monkeypatch):
    monkeypatch.setattr(auth_service, "create_access_token", lambda uid: "a")
    monkeypatch.setattr(auth_service, "create_refresh_token", lambda uid: "r")
    monkeypatch.setattr(auth_service, "decode_token", lambda tok, expected=None: {"jti": "j", "sub": "1"})
    monkeypatch.setattr(auth_service, "store_refresh", lambda uid, jti: None)
    monkeypatch.setattr(auth_service, "_role_ids", lambda db, uid: [])
    user = SimpleNamespace(id=1, username="alice", real_name="Alice", auth_source="oauth2", is_admin=0)
    tokens = auth_service.issue_tokens(_db(), user)
    assert set(tokens["user"]) == {"id", "username", "real_name", "roles"}

    monkeypatch.setattr(auth_service, "UserRepository", lambda db: SimpleNamespace(get=lambda i: user))
    monkeypatch.setattr(auth_service, "RoleRepository", lambda db: SimpleNamespace(get=lambda r: None, visible_group_ids=lambda r: []))
    monkeypatch.setattr(auth_service, "PermissionRepository", lambda db: SimpleNamespace(codes_by_user=lambda u: []))
    me = auth_service.me(_db(), 1)
    assert me["auth_source"] == "oauth2"
