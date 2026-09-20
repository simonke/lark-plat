"""P2-3 identity integration service: LDAP / OAuth2 SSO + provider management.

Add-only over phase-1 auth: external logins mint the same JWT pair and reuse the
existing RBAC/data-permission model. Provider config (incl. secrets) lives in
`auth_provider.config_enc` as a JSON string with **per-value** AES-GCM `enc:`
secrets (monitor-adapter style, architecture seq2090 v2.1); reads mask them.

Contract: api-design-v3 §3 note v2.1 + architecture-phase23 §5 (frozen
seq1843/1845/1760/2090).
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError, ValidationError
from app.core.redis_helper import (
    clear_login_failures,
    consume_oauth_state,
    record_login_failure,
    store_oauth_state,
)
from app.core.security import decrypt_secret, encrypt_secret, hash_password, mask_secret
from app.db.models import AuditLog, AuthProvider, ConfigRule, User, UserRole
from app.repositories import (
    AuthProviderRepository,
    ConfigRuleRepository,
    RoleRepository,
    UserRepository,
)
from app.schemas import system as sch
from app.services import auth_service

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL = 300
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SECRET_KEYS = {"password", "client_secret", "secret", "token"}
# Privileged role codes: an SSO provider may grant them explicitly, but only with
# an audit trail; the platform default must never apply them silently (seq2068 O1).
_PRIVILEGED_ROLE_CODES = {"admin", "superadmin", "super_admin", "super"}
_REQUIRED_CONFIG = {
    "ldap": ("server_uri", "bind_dn", "bind_dn_template", "base_dn", "password"),
    "oauth2": (
        "authorization_endpoint",
        "token_endpoint",
        "client_id",
        "client_secret",
        "redirect_uri",
    ),
}


# ---------------------------------------------------------------- feature flag


def _feature_enabled(db: Session) -> bool:
    """`feature.sso` namespace: disabled only when explicitly turned off."""
    rule = ConfigRuleRepository(db).by_key("feature.sso")
    return not (rule and (rule.rule_value or {}).get("enabled") == 0)


def _config_rule(db: Session, key: str, default: Any) -> Any:
    rule = ConfigRuleRepository(db).by_key(key)
    if rule is None:
        return default
    return rule.rule_value.get("value", default) if isinstance(rule.rule_value, dict) else default


# ---------------------------------------------------------------- config codec
#
# Per-value AES-GCM ("enc:" prefix), monitor-adapter style (seq2090 v2.1):
# secret values are stored as "enc:"+ciphertext inside the config JSON, all other
# values verbatim. `config_enc` holds that JSON string (D1 NOT NULL). `config_mask`
# masks every "enc:" value; a PUT that omits a key or echoes a masked string keeps
# the stored ciphertext.


def _load_stored(provider: AuthProvider) -> dict[str, Any]:
    try:
        value = json.loads(provider.config_enc)
    except Exception:  # noqa: BLE001 - malformed/legacy -> empty
        return {}
    return value if isinstance(value, dict) else {}


def _dump_config(config: dict[str, Any]) -> str:
    return json.dumps(config, ensure_ascii=False)


def _decrypt_config_val(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("enc:"):
            try:
                out[key] = decrypt_secret(value[4:])
            except Exception:  # noqa: BLE001
                out[key] = ""
        elif isinstance(value, dict):
            out[key] = _decrypt_config_val(value)
        else:
            out[key] = value
    return out


def _decrypt_config(provider: AuthProvider) -> dict[str, Any]:
    return _decrypt_config_val(_load_stored(provider))


def _is_masked_secret(value: str) -> bool:
    """Read-side masked secret ("ab******yz"/"****"); never re-encrypt over it."""
    return "*" in value


def _encrypt_config_secrets(
    config: dict[str, Any], existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Encrypt secret-key values with AES-GCM, recursing into nested dicts.

    Missing/masked secrets are preserved from `existing` (seq2090 ③): a PUT that
    echoes `config_mask` (e.g. "ab******yz") must not overwrite the ciphertext.
    """
    merged = dict(existing or {})
    for key, value in config.items():
        if key in _SECRET_KEYS and isinstance(value, str):
            if value.startswith("enc:") or _is_masked_secret(value):
                merged[key] = merged.get(key, value)
            else:
                merged[key] = "enc:" + encrypt_secret(value)
        elif isinstance(value, dict):
            nested = merged.get(key) if isinstance(merged.get(key), dict) else {}
            merged[key] = _encrypt_config_secrets(value, nested)
        else:
            merged[key] = value
    return merged


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, str) and value.startswith("enc:"):
            out[key] = mask_secret(value[4:])
        elif isinstance(value, dict):
            out[key] = _mask_config(value)
        else:
            out[key] = value
    return out



# ---------------------------------------------------------------- serializers


def _provider_out(provider: AuthProvider) -> dict:
    return {
        "id": provider.id,
        "code": provider.code,
        "name": provider.name,
        "type": provider.type,
        "enabled": provider.enabled,
        "config_mask": _mask_config(_load_stored(provider)),
        "created_at": provider.created_at.isoformat() if provider.created_at else None,
    }


def list_providers(db: Session) -> list[dict]:
    return [_provider_out(p) for p in AuthProviderRepository(db).list_all()]


def login_methods(db: Session) -> list[dict]:
    """Login-page methods: built-in `local` + enabled external providers."""
    methods = [{"code": "local", "type": "local", "name": "账号密码"}]
    for provider in AuthProviderRepository(db).list_enabled():
        methods.append({"code": provider.code, "type": provider.type, "name": provider.name})
    return methods


# ---------------------------------------------------------------- slug / lookup


def _normalize_code(raw: str | None, name: str) -> str:
    candidate = (raw or "").strip().lower()
    if not candidate:
        candidate = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not _CODE_RE.match(candidate):
        raise BadRequestError("invalid provider code (expected [a-z0-9_-], <=64)")
    return candidate


def _get_provider(db: Session, provider_id: int) -> AuthProvider:
    provider = AuthProviderRepository(db).get(provider_id)
    if provider is None:
        raise NotFoundError("provider not found")
    return provider


def _get_enabled_by_code(db: Session, code: str, expected_type: str | None = None) -> AuthProvider:
    provider = AuthProviderRepository(db).by_code(code)
    if provider is None or provider.enabled != 1:
        raise NotFoundError("provider not found or disabled")
    if expected_type and provider.type != expected_type:
        raise BadRequestError(f"provider {code} is not a {expected_type} provider")
    return provider


def _is_privileged(code: str) -> bool:
    return code.strip().lower() in _PRIVILEGED_ROLE_CODES


def _validate_role_codes(db: Session, codes: list[str] | None) -> list[str]:
    """Validate provider-declared default_role_codes (seq2068 O1).

    Unknown/illegal code -> 422. Returns the privileged codes present (allowed
    explicitly, but the caller must record an audit trail)."""
    if not codes:
        return []
    role_repo = RoleRepository(db)
    privileged: list[str] = []
    for code in codes:
        if role_repo.by_code(code) is None:
            raise ValidationError(f"unknown role code: {code}")
        if _is_privileged(code):
            privileged.append(code)
    return privileged


def _audit_privileged_grant(
    db: Session, actor, provider_code: str, codes: list[str], action: str
) -> None:
    """Mandatory audit when a provider explicitly grants admin/super roles."""
    db.execute(
        AuditLog.__table__.insert().values(
            user_id=getattr(actor, "id", None),
            username=getattr(actor, "username", "") or "",
            module="auth",
            action=action,
            method="PUT",
            path="/api/v1/auth/providers",
            params={"provider_code": provider_code, "default_role_codes": codes, "privileged": True},
            ip="",
            user_agent="",
            status=1,
            cost_ms=0,
            trace_id="",
        )
    )


# ---------------------------------------------------------------- provider CRUD


def create_provider(db: Session, actor, data: sch.AuthProviderCreate) -> dict:
    if not _feature_enabled(db):
        raise BadRequestError("sso feature disabled")
    if data.type not in ("ldap", "oauth2"):
        raise ValidationError(f"invalid provider type: {data.type}")
    repo = AuthProviderRepository(db)
    code = _normalize_code(data.code, data.name)
    if repo.by_code(code) is not None:
        raise BadRequestError(f"provider code already exists: {code}")
    privileged = _validate_role_codes(db, (data.config or {}).get("default_role_codes"))
    provider = AuthProvider(
        code=code,
        name=data.name,
        type=data.type,
        config_enc=_dump_config(_encrypt_config_secrets(data.config or {}, None)),
        enabled=data.enabled,
    )
    repo.add(provider)
    if privileged:
        _audit_privileged_grant(db, actor, code, privileged, "sso.provider.privileged_roles")
    db.commit()
    return _provider_out(provider)


def update_provider(db: Session, actor, provider_id: int, data: sch.AuthProviderUpdate) -> dict:
    provider = _get_provider(db, provider_id)
    if data.name is not None:
        provider.name = data.name
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.config is not None:
        privileged = _validate_role_codes(db, data.config.get("default_role_codes"))
        existing = _load_stored(provider)
        provider.config_enc = _dump_config(_encrypt_config_secrets(data.config, existing))
        if privileged:
            _audit_privileged_grant(
                db, actor, provider.code, privileged, "sso.provider.privileged_roles"
            )
    db.commit()
    return _provider_out(provider)


def delete_provider(db: Session, provider_id: int) -> dict:
    provider = _get_provider(db, provider_id)
    db.delete(provider)
    db.commit()
    return {"id": provider_id, "deleted": True}


def set_provider_status(db: Session, provider_id: int, enabled: int) -> dict:
    provider = _get_provider(db, provider_id)
    provider.enabled = enabled
    db.commit()
    return {"id": provider.id, "enabled": provider.enabled}


def _config_required_present(provider: AuthProvider, config: dict) -> str | None:
    for key in _REQUIRED_CONFIG.get(provider.type, ()):
        if not config.get(key):
            return key
    return None


def test_provider(db: Session, provider_id: int) -> dict:
    provider = _get_provider(db, provider_id)
    config = _decrypt_config(provider)
    missing = _config_required_present(provider, config)
    if missing:
        return {"ok": False, "latency_ms": None, "error_message": f"missing config: {missing}"}
    if provider.type == "ldap":
        return _test_ldap(config)
    return _test_oauth2(config)


def _test_ldap(config: dict) -> dict:
    started = time.perf_counter()
    try:
        import ldap3
    except ImportError:  # pragma: no cover - dependency declared in pyproject
        return {"ok": False, "latency_ms": None, "error_message": "ldap3 not installed"}
    try:
        server = ldap3.Server(config["server_uri"], get_info=ldap3.NONE, connect_timeout=5)
        user = config.get("bind_dn")
        password = config.get("password")
        conn = ldap3.Connection(server, user=user, password=password, receive_timeout=5)
        ok = bool(conn.bind())
        conn.unbind()
        return _test_result(ok, started, None if ok else "bind failed")
    except Exception as exc:  # noqa: BLE001
        return _test_result(False, started, str(exc)[:512])


def _test_oauth2(config: dict) -> dict:
    started = time.perf_counter()
    try:
        resp = httpx.get(config["token_endpoint"], timeout=5)
        ok = resp.status_code < 500
        return _test_result(ok, started, None if ok else f"HTTP {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        return _test_result(False, started, str(exc)[:512])


def _test_result(ok: bool, started: float, error_message: str | None) -> dict:
    return {"ok": ok, "latency_ms": int((time.perf_counter() - started) * 1000), "error_message": error_message}


# ---------------------------------------------------------------- identity map/provision


def _resolve_external_user(
    db: Session, provider: AuthProvider, map_value: str, profile: dict
) -> User:
    """Map an external identity to a local user, provisioning when allowed."""
    if not map_value:
        raise UnauthorizedError("identity provider returned no subject")
    repo = UserRepository(db)
    map_key = (profile.get("map_key") or "username").lower()
    user = repo.by_email(map_value) if map_key == "email" else repo.by_username(map_value)
    auto_provision = profile.get("auto_provision")
    if auto_provision is None:
        auto_provision = _config_rule(db, "sso.auto_provision", False)
    if user is None:
        if not auto_provision:
            raise UnauthorizedError("user not provisioned")
        user = User(
            username=map_value[:64],
            password_hash=hash_password(secrets.token_urlsafe(24)),
            real_name=(profile.get("display_name") or map_value)[:64],
            email=(profile.get("email") or None),
            status=1,
            is_admin=0,
            auth_source=provider.type,
            external_id=str(profile.get("external_id") or map_value),
            last_external_login_at=datetime.now(timezone.utc),
        )
        repo.add(user)
        db.flush()
        _bind_default_roles(db, user, profile)
        return user
    if user.deleted or user.status != 1:
        raise UnauthorizedError("user disabled or missing")
    user.auth_source = provider.type
    user.external_id = str(profile.get("external_id") or map_value)
    user.last_external_login_at = datetime.now(timezone.utc)
    return user


def _claim_roles(config: dict, attrs: dict) -> list[str] | None:
    """Resolve role codes from the IdP response via the optional `roles_claim` key
    (names the claim/attribute carrying role codes). IdP-supplied roles are runtime
    input, so `_bind_default_roles` refuses privileged codes in them (seq2068 O1)."""
    claim = config.get("roles_claim")
    if not claim:
        return None
    raw = attrs.get(claim)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple, set)):
        return [str(item) for item in raw]
    return [str(raw)]


def _bind_default_roles(db: Session, user: User, profile: dict) -> None:
    """Bind default roles to a newly provisioned external user.

    Provider-declared codes (explicit, already 422-validated + audited on the
    provider write) are applied as-is. Runtime sources (IdP `roles_claim` or the
    platform `config_rule sso.default_role_codes`) must never apply admin/super
    silently -> privileged codes are refused and logged (seq2068 O1)."""
    explicit = profile.get("default_role_codes")
    if explicit is not None:
        codes = explicit
    else:
        codes = profile.get("claim_roles")
        if codes is None:
            codes = _config_rule(db, "sso.default_role_codes", []) or []
        refused = [c for c in codes if _is_privileged(c)]
        if refused:
            logger.warning(
                "sso: runtime default_role_codes contains privileged %s; refused (not applied)",
                refused,
            )
        codes = [c for c in codes if not _is_privileged(c)]
    role_repo = RoleRepository(db)
    for code in codes or []:
        role = role_repo.by_code(code)
        if role is not None:
            db.add(UserRole(user_id=user.id, role_id=role.id))


def _finish_external_login(db: Session, username: str, user: User) -> dict:
    clear_login_failures(username)
    user.last_login_at = datetime.now(timezone.utc)
    result = auth_service.issue_tokens(db, user)
    db.commit()
    return result


# ---------------------------------------------------------------- LDAP login


def _ldap_attributes(provider: AuthProvider, username: str, password: str) -> dict:
    import ldap3

    config = _decrypt_config(provider)
    server = ldap3.Server(config["server_uri"], get_info=ldap3.NONE, connect_timeout=5)
    bind_dn = config["bind_dn_template"].format(username=username)
    conn = ldap3.Connection(server, user=bind_dn, password=password, receive_timeout=5, auto_bind=True)
    try:
        conn.search(
            config.get("base_dn", ""),
            config.get("filter", "(objectClass=person)"),
            attributes=ldap3.ALL_ATTRIBUTES,
            size_limit=1,
        )
        if not conn.entries:
            raise UnauthorizedError("invalid username or password")
        entry = conn.entries[0]
        attrs = {str(attr.key): attr.value for attr in entry}
    finally:
        conn.unbind()
    return attrs


def _ldap_map_value(config: dict, attrs: dict, username: str) -> str:
    map_key = (config.get("map_key") or "username").lower()
    if map_key == "email":
        return str(attrs.get("mail") or attrs.get("email") or "")
    if map_key == "uid":
        return str(attrs.get("uid") or attrs.get("sAMAccountName") or username)
    return str(attrs.get("uid") or attrs.get("sAMAccountName") or username)


def ldap_login(db: Session, username: str, password: str) -> dict:
    if not _feature_enabled(db):
        raise BadRequestError("sso feature disabled")
    providers = [p for p in AuthProviderRepository(db).list_enabled() if p.type == "ldap"]
    if not providers:
        raise BadRequestError("ldap not configured")
    last_error: Exception | None = None
    for provider in providers:
        try:
            attrs = _ldap_attributes(provider, username, password)
        except UnauthorizedError as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001 - bind/search failure == auth failure
            last_error = exc
            continue
        config = _decrypt_config(provider)
        map_value = _ldap_map_value(config, attrs, username)
        profile = {
            "map_key": config.get("map_key", "username"),
            "email": attrs.get("mail") or attrs.get("email"),
            "display_name": attrs.get("displayName") or attrs.get("cn") or map_value,
            "external_id": attrs.get("uid") or attrs.get("sAMAccountName") or map_value,
            "auto_provision": config.get("auto_provision"),
            "default_role_codes": config.get("default_role_codes"),
            "roles_claim": config.get("roles_claim"),
            "claim_roles": _claim_roles(config, attrs),
        }
        user = _resolve_external_user(db, provider, map_value, profile)
        return _finish_external_login(db, username, user)
    record_login_failure(username)
    raise UnauthorizedError("invalid username or password") from last_error


# ---------------------------------------------------------------- OAuth2


def _redirect_uri(request_base: str, code: str) -> str:
    return f"{request_base.rstrip('/')}{settings.api_prefix}/auth/oauth/{code}/callback"


def oauth_authorize_url(db: Session, code: str, request_base: str) -> str:
    provider = _get_enabled_by_code(db, code, "oauth2")
    config = _decrypt_config(provider)
    redirect_uri = config.get("redirect_uri") or _redirect_uri(request_base, code)
    state = secrets.token_urlsafe(24)
    store_oauth_state(state, {"code": code, "redirect_uri": redirect_uri}, OAUTH_STATE_TTL)
    params = {
        "response_type": "code",
        "client_id": config["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if config.get("scope"):
        params["scope"] = config["scope"]
    sep = "&" if "?" in config["authorization_endpoint"] else "?"
    return f"{config['authorization_endpoint']}{sep}{urlencode(params)}"


def _oauth_exchange(config: dict, code: str, redirect_uri: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": config["client_id"],
        "client_secret": config.get("client_secret", ""),
    }
    resp = httpx.post(config["token_endpoint"], data=data, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise UnauthorizedError("token endpoint returned no access_token")
    return token


def _oauth_profile(config: dict, access_token: str) -> dict:
    url = config.get("userinfo_endpoint")
    if not url:
        raise BadRequestError("oauth2 provider missing userinfo_endpoint")
    resp = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    return resp.json()


def oauth_callback(db: Session, code: str, auth_code: str, state: str) -> dict:
    if not _feature_enabled(db):
        raise BadRequestError("sso feature disabled")
    provider = _get_enabled_by_code(db, code, "oauth2")
    cached = consume_oauth_state(state)
    if not cached or cached.get("code") != code:
        raise BadRequestError("invalid or expired state")
    config = _decrypt_config(provider)
    redirect_uri = cached.get("redirect_uri") or config.get("redirect_uri") or ""
    access_token = _oauth_exchange(config, auth_code, redirect_uri)
    raw = _oauth_profile(config, access_token)
    map_key = (config.get("map_key") or "username").lower()
    attrs = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    map_value = str(attrs.get(map_key) or attrs.get("email") or attrs.get("sub") or "")
    profile = {
        "map_key": map_key,
        "email": attrs.get("email"),
        "display_name": attrs.get("name") or attrs.get("display_name") or map_value,
        "external_id": attrs.get("sub") or map_value,
        "auto_provision": config.get("auto_provision"),
        "default_role_codes": config.get("default_role_codes"),
        "roles_claim": config.get("roles_claim"),
        "claim_roles": _claim_roles(config, attrs),
    }
    user = _resolve_external_user(db, provider, map_value, profile)
    result = _finish_external_login(db, map_value or user.username, user)
    result["provider"] = {"code": provider.code, "type": provider.type, "name": provider.name}
    result["redirect_after"] = frontend_callback_url(db, config)
    return result


def frontend_callback_url(db: Session, config: dict | None = None) -> str | None:
    """Primary: config_rule sso.frontend_callback_url; provider `redirect_after`
    override; env SSO_FRONTEND_CALLBACK_URL fallback. None => JSON mode."""
    if config and config.get("redirect_after"):
        return config["redirect_after"]
    value = _config_rule(db, "sso.frontend_callback_url", None)
    return value or (settings.sso_frontend_callback_url or None)
