"""P2-3 identity integration service: LDAP / OAuth2 SSO + provider management.

Add-only over phase-1 auth: external logins mint the same JWT pair and reuse the
existing RBAC/data-permission model. Provider secrets live in
`auth_provider.config_enc` (whole-config AES-GCM, same envelope as
notify_channel.config_enc); reads mask them.

Contract: api-design-v3 §3 + architecture-phase23 §5 (frozen seq1843/1845/1760).
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.core.redis_helper import (
    clear_login_failures,
    consume_oauth_state,
    record_login_failure,
    store_oauth_state,
)
from app.core.security import decrypt_secret, encrypt_secret, hash_password
from app.db.models import AuthProvider, ConfigRule, User, UserRole
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
_SECRET_KEYS = {"password", "bind_password", "client_secret", "secret", "token"}
_REQUIRED_CONFIG = {
    "ldap": ("server_uri", "bind_dn_template", "base_dn"),
    "oauth2": ("authorize_url", "token_url", "client_id"),
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


# ---------------------------------------------------------------- config crypto


def _decrypt_config(provider: AuthProvider) -> dict[str, Any]:
    try:
        return json.loads(decrypt_secret(provider.config_enc))
    except Exception:  # noqa: BLE001 - malformed/plaintext legacy -> empty
        return {}


def _encrypt_config(config: dict[str, Any]) -> str:
    return encrypt_secret(json.dumps(config, ensure_ascii=False))


def _mask_value(key: str, value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _mask_value(k, v) for k, v in value.items()}
    if key in _SECRET_KEYS and isinstance(value, str) and value:
        return "****" if len(value) <= 4 else value[:2] + "****"
    return value


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    return {k: _mask_value(k, v) for k, v in config.items()}


def _resolve_config_incoming(incoming: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    """A PUT that echoes back a masked secret ("ab****") keeps the stored value."""
    merged = dict(incoming)
    for key, value in list(merged.items()):
        if key in _SECRET_KEYS and isinstance(value, str) and "*" in value:
            if key in existing:
                merged[key] = existing[key]
            else:
                merged.pop(key, None)
    return merged


# ---------------------------------------------------------------- serializers


def _provider_out(provider: AuthProvider) -> dict:
    return {
        "id": provider.id,
        "code": provider.code,
        "name": provider.name,
        "type": provider.type,
        "enabled": provider.enabled,
        "config_mask": _mask_config(_decrypt_config(provider)),
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


# ---------------------------------------------------------------- provider CRUD


def create_provider(db: Session, data: sch.AuthProviderCreate) -> dict:
    if not _feature_enabled(db):
        raise BadRequestError("sso feature disabled")
    if data.type not in ("ldap", "oauth2"):
        raise BadRequestError(f"invalid provider type: {data.type}")
    repo = AuthProviderRepository(db)
    code = _normalize_code(data.code, data.name)
    if repo.by_code(code) is not None:
        raise BadRequestError(f"provider code already exists: {code}")
    provider = AuthProvider(
        code=code,
        name=data.name,
        type=data.type,
        config_enc=_encrypt_config(data.config or {}),
        enabled=data.enabled,
    )
    repo.add(provider)
    db.commit()
    return _provider_out(provider)


def update_provider(db: Session, provider_id: int, data: sch.AuthProviderUpdate) -> dict:
    provider = _get_provider(db, provider_id)
    if data.name is not None:
        provider.name = data.name
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.config is not None:
        existing = _decrypt_config(provider)
        provider.config_enc = _encrypt_config(_resolve_config_incoming(data.config, existing))
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
        return {"ok": False, "type": provider.type, "error_message": f"missing config: {missing}"}
    if provider.type == "ldap":
        return _test_ldap(config)
    return _test_oauth2(config)


def _test_ldap(config: dict) -> dict:
    try:
        import ldap3
    except ImportError:  # pragma: no cover - dependency declared in pyproject
        return {"ok": False, "type": "ldap", "error_message": "ldap3 not installed"}
    try:
        server = ldap3.Server(config["server_uri"], get_info=ldap3.NONE, connect_timeout=5)
        user = config.get("bind_dn")
        password = config.get("bind_password")
        conn = ldap3.Connection(server, user=user, password=password, receive_timeout=5)
        ok = bool(conn.bind())
        conn.unbind()
        return {"ok": ok, "type": "ldap", "error_message": None if ok else "bind failed"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "type": "ldap", "error_message": str(exc)[:512]}


def _test_oauth2(config: dict) -> dict:
    try:
        resp = httpx.get(config["token_url"], timeout=5)
        ok = resp.status_code < 500
        return {"ok": ok, "type": "oauth2", "error_message": None if ok else f"HTTP {resp.status_code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "type": "oauth2", "error_message": str(exc)[:512]}


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


def _bind_default_roles(db: Session, user: User, profile: dict) -> None:
    codes = profile.get("default_role_codes")
    if codes is None:
        codes = _config_rule(db, "sso.default_role_codes", [])
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
    sep = "&" if "?" in config["authorize_url"] else "?"
    return f"{config['authorize_url']}{sep}{urlencode(params)}"


def _oauth_exchange(config: dict, code: str, redirect_uri: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": config["client_id"],
        "client_secret": config.get("client_secret", ""),
    }
    resp = httpx.post(config["token_url"], data=data, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    token = payload.get("access_token")
    if not token:
        raise UnauthorizedError("token endpoint returned no access_token")
    return token


def _oauth_profile(config: dict, access_token: str) -> dict:
    url = config.get("userinfo_url")
    if not url:
        raise BadRequestError("oauth2 provider missing userinfo_url")
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
