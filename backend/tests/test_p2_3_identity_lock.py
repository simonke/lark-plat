"""P2-ID (P2-3 identity integration) contract locks — @单元测试工程师.

Frozen contract: api-design-v3 §3 note **v2** (架构 seq2056, corrects seq2049) +
architecture-phase23 §5.2; rulings P2-3-A (seq1843) / P2-3-B (seq1845) / Q1-A
(seq1847); acceptance checklist §22 (需求 seq2039, item2/3/4 frozen seq2058);
reviewer §20.6 lock (seq2040/2053/2057). Baseline master = `4294c63` (pushed);
rebase tip = `4597881` (parent `4294c63`; M1 fixed). v2 secret keys are
`password`(LDAP)/`client_secret`(OAuth2) INSIDE the `config` JSON, plus
`auto_provision`/`default_role_codes`/`map_key`(whitelist, forbids
`is_admin`/`password_hash`) — these are payload keys, not response-model fields,
so they are exercised by the reviewer §20.6 runtime lock, not this schema lock.

EXPECTED: D*/M*/P*/S* GREEN once the rebased P2-ID branch lands (data layer is
already frozen); A1 (openapi runtime surface) RED until the §3 nine endpoints
are implemented. Run from the backend checkout:
    pytest tests/... -p no:cacheprovider   (or -q with external cwd=backend)

Pins
----
D1  auth_provider model/table: `code` UNIQUE, `config_enc` Text, `enabled` int;
    AUTH_PROVIDER_TYPES == ("ldap", "oauth2"); AUTH_SOURCES == ("local","ldap","oauth2").
D2  sys_user add-only: auth_source (default 'local', server_default 'local'),
    external_id (nullable), last_external_login_at (nullable tz datetime).
D3  schemas: AuthProviderOut (admin variant) ⊇ {id,code,type,name,enabled,config_mask,
    created_at} with NO plaintext `config` and NO secret/token field (arch §3 note
    item1, seq2049); AuthProviderBrief is EXACTLY {code,type,name}; LdapLoginIn
    {username,password}; AuthProviderCreate/Update/StatusIn shapes.
    (R3/R4 runtime assertions — enc:/mask round-trip, PUT mask keeps ciphertext,
    redirect Location whitelist, /test keys — are reviewer §20.6 lock scope, not here.)
M1  migration revision `c3d4e5f6a7b8`.down_revision == `d4e5f6a7b8c9` and the
    full chain has exactly ONE head (no dual head). [测试维护: the global head
    moved to `e8a1b2c3d4f5` when the P2 收口批 item1 dedup migration appended
    after `c3d4e5f6a7b8`; the single-head invariant is preserved generically.]
P1  permission point `system:auth:provider` registered in the seed PERMISSION_TREE.
A1  openapi paths count == 107 (100 baseline + 7 UNIQUE URL keys covering the §3
    nine operations: GET+POST /auth/providers share one key, PUT+DELETE
    /auth/providers/{id} share one key), `/monitor/*` == 19, and all nine
    provider/ldap/oauth operations exist with the correct method. (OpenAPI
    `paths` is URL-keyed, so "100->109" is an operations count, not path keys;
    flagged to 架构 seq2072 for ruling — if a separate admin path is required,
    count becomes 108/109.)
S1  AES-GCM helpers encrypt_secret/decrypt_secret round-trip (config_enc seam).
C1  app.services.sso_service consumes the FROZEN v2.1 config keys —
    LDAP `bind_dn`(service account DN) + `password`(secret) + mandatory
    {server_uri,bind_dn,bind_dn_template,base_dn,password}; OAuth2
    `authorization_endpoint`/`token_endpoint`/`userinfo_endpoint` + mandatory
    {authorization_endpoint,token_endpoint,client_id,client_secret,redirect_uri}
    — and NOT the v1 names `bind_password`/`authorize_url`/`token_url`/
    `userinfo_url` (架构 seq2090 v2.1; 需求 seq2084/2087; frontend seq2086).
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path
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


def _require(value, what: str):
    if value is None:
        pytest.fail(f"P2-ID lock: {what} not available yet (EXPECTED RED until rebased branch lands)")


def _auth_provider_module():
    return _try("app.db.models.auth_provider")


# ── D1: auth_provider model surface ──────────────────────────────────────────

def test_d1_auth_provider_table_and_columns():
    mod = _auth_provider_module()
    if isinstance(mod, Exception):
        pytest.fail(f"P2-ID lock: app.db.models.auth_provider unavailable: {mod}")
    AuthProvider = getattr(mod, "AuthProvider", None)
    _require(AuthProvider, "AuthProvider model")
    tbl = AuthProvider.__table__
    assert tbl.name == "auth_provider", tbl.name
    cols = tbl.columns
    for name in ("id", "code", "name", "type", "config_enc", "enabled"):
        assert name in cols, f"auth_provider missing column {name!r}; have {list(cols)}"
    assert cols["code"].unique is True, "auth_provider.code must be UNIQUE (routing key)"
    assert not cols["config_enc"].nullable, "config_enc must be NOT NULL (secrets envelope)"
    assert cols["enabled"].server_default is not None, (
        "reviewer seq2040: auth_provider.enabled must carry server_default to match "
        "migration '1' (avoid autogenerate drift)")


def test_d1_provider_types_and_sources():
    mod = _auth_provider_module()
    if isinstance(mod, Exception):
        pytest.fail(f"P2-ID lock: app.db.models.auth_provider unavailable: {mod}")
    assert tuple(getattr(mod, "AUTH_PROVIDER_TYPES", ())) == ("ldap", "oauth2")
    assert tuple(getattr(mod, "AUTH_SOURCES", ())) == ("local", "ldap", "oauth2")


# ── D2: sys_user additive identity columns ───────────────────────────────────

def test_d2_user_additive_auth_columns():
    User, exc = None, None
    try:
        from app.db.models import User  # type: ignore
    except Exception as e:  # noqa: BLE001
        exc = e
    if exc is not None:
        pytest.fail(f"P2-ID lock: app.db.models.User unavailable: {exc}")
    cols = User.__table__.columns
    for name in ("auth_source", "external_id", "last_external_login_at"):
        assert name in cols, f"sys_user missing add-only column {name!r}"
    dflt = cols["auth_source"].default
    assert dflt is not None and getattr(dflt, "arg", None) == "local", (
        "sys_user.auth_source python default must be 'local'")
    sd = cols["auth_source"].server_default
    assert sd is not None and "local" in str(getattr(sd, "arg", sd)), (
        "sys_user.auth_source server_default must be 'local'")
    assert cols["external_id"].nullable is True
    assert cols["last_external_login_at"].nullable is True


# ── D3: schema shapes (frozen) ───────────────────────────────────────────────

def _schema(name: str):
    try:
        from app.schemas import system as sys_schemas
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-ID lock: app.schemas.system unavailable: {exc}")
    return getattr(sys_schemas, name, None)


def test_d3_auth_provider_out_has_config_mask_not_config():
    Out = _schema("AuthProviderOut")
    _require(Out, "schemas.system.AuthProviderOut")
    fields = set(Out.model_fields)
    assert "config_mask" in fields, f"AuthProviderOut must expose config_mask; have {sorted(fields)}"
    assert "config" not in fields, (
        "AuthProviderOut must NEVER expose plaintext `config` (US-03; use config_mask)")
    # admin/authorized variant exact superset, frozen by arch §3 note item1 (seq2049)
    admin = {"id", "code", "type", "name", "enabled", "config_mask", "created_at"}
    missing = admin - fields
    assert not missing, f"AuthProviderOut (admin variant) missing frozen fields: {sorted(missing)}"
    leaked = {
        "config_enc", "config", "login_path",  # secrets envelope / internal fields
        "password", "bind_password", "client_secret",  # per-provider secret keys (v2)
        "access_token", "refresh_token",  # never echoed
    }
    assert not (leaked & fields), (
        f"AuthProviderOut must not leak secret/token/internal fields: {sorted(leaked & fields)}")


def test_d3_brief_exact_fields():
    Brief = _schema("AuthProviderBrief")
    _require(Brief, "schemas.system.AuthProviderBrief")
    assert set(Brief.model_fields) == {"code", "type", "name"}, (
        f"AuthProviderBrief must be exactly {{code,type,name}} (P2-3-A, no login_path); "
        f"got {sorted(Brief.model_fields)}")
    forbidden = {"id", "enabled", "config_mask", "config", "created_at", "config_enc", "login_path"}
    assert not (forbidden & set(Brief.model_fields)), (
        "anonymous/login-page provider entry must not leak admin-only keys; "
        f"leaked={sorted(forbidden & set(Brief.model_fields))}")


def test_d3_ldap_login_in_fields():
    In = _schema("LdapLoginIn")
    _require(In, "schemas.system.LdapLoginIn")
    assert set(In.model_fields) == {"username", "password"}, sorted(In.model_fields)


def test_d3_create_update_status_shapes():
    Create = _schema("AuthProviderCreate")
    Update = _schema("AuthProviderUpdate")
    Status = _schema("AuthProviderStatusIn")
    _require(Create, "AuthProviderCreate")
    _require(Update, "AuthProviderUpdate")
    _require(Status, "AuthProviderStatusIn")
    assert {"name", "type", "config", "enabled"} <= set(Create.model_fields)
    assert "config" in Update.model_fields and Update.model_fields["config"].default is None, (
        "AuthProviderUpdate.config omit(None) must mean 'keep existing ciphertext'")
    assert "enabled" in Status.model_fields


# ── M1: migration chain / single head ────────────────────────────────────────

def _versions_dir() -> Path:
    import app  # noqa: PLC0415

    return Path(app.__file__).resolve().parent.parent / "alembic" / "versions"


def _revisions() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for f in _versions_dir().glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(None|["\']([^"\']*)["\'])', text, re.M)
        if not rev:
            continue
        d = None
        if down:
            d = None if down.group(1) == "None" else down.group(2)
        out.append((rev.group(1), d))
    return out


def _chain_from_head(head: str, by_rev: dict) -> set[str]:
    seen: set[str] = set()
    cur: str | None = head
    while cur and cur not in seen:
        seen.add(cur)
        cur = by_rev.get(cur)
    return seen


def test_m1_down_revision_moved_and_single_head():
    revs = _revisions()
    _require(revs, "alembic revisions")
    by_rev = dict(revs)
    assert "c3d4e5f6a7b8" in by_rev, "P2-ID migration c3d4e5f6a7b8 missing"
    assert by_rev["c3d4e5f6a7b8"] == "d4e5f6a7b8c9", (
        "P2-3-B: c3d4e5f6a7b8.down_revision MUST be 'd4e5f6a7b8c9' (else dual head); "
        f"got {by_rev['c3d4e5f6a7b8']!r}")
    downs = {d for _, d in revs if d}
    heads = {r for r, _ in revs if r not in downs}
    # Head-agnostic (close-out batch appends migrations onto c3d4e5f6a7b8): require a
    # single head and that the P2-ID migration remains on that head's ancestry chain.
    assert len(heads) == 1, f"alembic must have exactly one head; got heads={sorted(heads)}"
    head = next(iter(heads))
    chain = _chain_from_head(head, by_rev)
    assert "c3d4e5f6a7b8" in chain, (
        f"P2-ID migration c3d4e5f6a7b8 must stay on the single head chain; "
        f"head={head!r}, chain={sorted(chain)}")


# ── P1: permission point registered ─────────────────────────────────────────

def _walk_perms(tree, acc):
    for node in tree:
        acc.add(node[0])
        children = node[5] if len(node) > 5 else []
        if children:
            _walk_perms(children, acc)


def test_p1_permission_point_system_auth_provider():
    try:
        from app.db import seed
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-ID lock: app.db.seed unavailable: {exc}")
    acc: set[str] = set()
    _walk_perms(getattr(seed, "PERMISSION_TREE", []), acc)
    assert "system:auth:provider" in acc, (
        "permission point 'system:auth:provider' must be registered in PERMISSION_TREE")


# ── A1: openapi runtime surface (§3 nine endpoints; 100 -> 109) ──────────────

def _openapi_paths():
    try:
        from app.main import app
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-ID lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def _has(paths, regex: str) -> bool:
    return any(re.fullmatch(regex, p) for p in paths)


def test_a1_paths_count_107_and_monitor_19():
    paths = _openapi_paths()
    monitor = [p for p in paths if "/monitor" in p]
    assert len(paths) == 107, (
        "openapi paths must be 100->107 after P2-ID (7 unique URL keys for the §3 "
        f"nine operations); got {len(paths)}")
    assert len(monitor) == 19, f"/monitor/* must stay 19 (frozen P2-MA); got {len(monitor)}"


def test_a1_provider_and_auth_paths_present():
    paths = _openapi_paths()
    checks = {
        "GET /auth/providers": (r"/api/v1/auth/providers", "get"),
        "POST /auth/providers": (r"/api/v1/auth/providers", "post"),
        "PUT /auth/providers/{id}": (r"/api/v1/auth/providers/\{[^}]+\}", "put"),
        "DELETE /auth/providers/{id}": (r"/api/v1/auth/providers/\{[^}]+\}", "delete"),
        # api-design-v3 §3:147 -> PUT (启停); frontend p2-3-auth:71e54ee uses PUT
        "PUT /auth/providers/{id}/status": (r"/api/v1/auth/providers/\{[^}]+\}/status", "put"),
        "POST /auth/providers/{id}/test": (r"/api/v1/auth/providers/\{[^}]+\}/test", "post"),
        "POST /auth/ldap/login": (r"/api/v1/auth/ldap/login", "post"),
        "GET /auth/oauth/{p}/login": (r"/api/v1/auth/oauth/\{[^}]+\}/login", "get"),
        "GET /auth/oauth/{p}/callback": (r"/api/v1/auth/oauth/\{[^}]+\}/callback", "get"),
    }
    missing = []
    for label, (regex, method) in checks.items():
        hit = next((p for p in paths if re.fullmatch(regex, p)), None)
        if hit is None or method not in paths[hit]:
            missing.append(label)
    assert not missing, f"§3 endpoints missing/wrong-method: {missing}"


def test_a1_providers_list_returns_brief_shape(monkeypatch):
    """Login-page provider list entries are EXACTLY {code,type,name} (incl. built-in
    local) with no login_path. Locked at the schema level (AuthProviderBrief)."""
    Brief = _schema("AuthProviderBrief")
    _require(Brief, "AuthProviderBrief")
    payload = Brief(code="local", type="local", name="本地登录").model_dump()
    assert set(payload) == {"code", "type", "name"}, payload


# ── S1: crypto seam for config_enc ───────────────────────────────────────────

def test_s1_encrypt_secret_roundtrip():
    try:
        from app.core.security import decrypt_secret, encrypt_secret
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-ID lock: crypto helpers unavailable: {exc}")
    plain = '{"client_secret": "p@ssw0rd"}'
    token = encrypt_secret(plain)
    assert token != plain, "config_enc must be ciphertext, never plaintext"
    assert decrypt_secret(token) == plain, "config_enc AES-GCM round-trip must hold"


# ── C1: service reads the FROZEN v2 provider-config key names ────────────────
# §3 note v2 (架构 seq2056) + contract §3:157-159 (需求 seq2084): the service MUST
# consume `password` (LDAP secret) and `authorization_endpoint` / `token_endpoint`
# / `userinfo_endpoint` (OAuth2), never the v1 names `bind_password` / `bind_dn`
# / `authorize_url` / `token_url` / `userinfo_url` (frontend seq2086).

# v2.1 (架构 seq2090): `bind_dn` is a LEGAL LDAP key again (service-account DN),
# so it is NOT in the forbidden set; only these v1 names remain banned.
_V1_CONFIG_KEYS = (
    r"\bbind_password\b",   # renamed to `password`
    r"\bauthorize_url\b",   # -> authorization_endpoint
    r"\btoken_url\b",       # -> token_endpoint (does NOT match secrets.token_urlsafe)
    r"\buserinfo_url\b",    # -> userinfo_endpoint
)
_LDAP_REQUIRED = {"server_uri", "bind_dn", "bind_dn_template", "base_dn", "password"}
_OAUTH2_REQUIRED = {
    "authorization_endpoint", "token_endpoint", "client_id", "client_secret", "redirect_uri",
}


def test_c1_service_uses_v2_config_keys_not_v1():
    mod = _try("app.services.sso_service")
    if isinstance(mod, Exception):
        pytest.fail(f"P2-ID lock: app.services.sso_service unavailable: {mod}")
    src = inspect.getsource(mod)
    legacy = [pat for pat in _V1_CONFIG_KEYS if re.search(pat, src)]
    assert not legacy, (
        "sso_service still references v1 provider-config keys; freeze v2.1 uses "
        "`password`(LDAP) + `authorization_endpoint`/`token_endpoint`/"
        f"`userinfo_endpoint`(OAuth2): still-present={legacy}")
    required = (
        "bind_dn", "bind_dn_template", "base_dn", "map_key", "auto_provision",
        "default_role_codes", "authorization_endpoint", "token_endpoint",
        "userinfo_endpoint", "client_secret", "redirect_uri", "roles_claim",
    )
    missing = [k for k in required if k not in src]
    assert not missing, f"sso_service must reference v2.1 config keys; missing={missing}"


def test_c1_required_config_uses_v2_mandatory_keys():
    """architecture seq2090 ①②: mandatory-config gates use the v2.1 key names."""
    mod = _try("app.services.sso_service")
    if isinstance(mod, Exception):
        pytest.fail(f"P2-ID lock: app.services.sso_service unavailable: {mod}")
    req = getattr(mod, "_REQUIRED_CONFIG", None)
    if req is None:
        pytest.fail("P2-ID lock: sso_service._REQUIRED_CONFIG not available")
    ldap_req = set(req.get("ldap", ()))
    oauth_req = set(req.get("oauth2", ()))
    assert _LDAP_REQUIRED <= ldap_req, (
        f"LDAP mandatory keys must include {sorted(_LDAP_REQUIRED)}; got {sorted(ldap_req)}")
    assert _OAUTH2_REQUIRED <= oauth_req, (
        f"OAuth2 mandatory keys must include {sorted(_OAUTH2_REQUIRED)}; got {sorted(oauth_req)}")
    banned = {"bind_password", "authorize_url", "token_url", "userinfo_url"}
    leaked = banned & (ldap_req | oauth_req)
    assert not leaked, f"mandatory-config still uses v1 keys: {sorted(leaked)}"
