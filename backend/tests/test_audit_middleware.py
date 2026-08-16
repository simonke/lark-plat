"""Audit middleware unit tests (US-11): redaction + append-only posture.

The DB-level UPDATE/DELETE revocation lives in deploy/init.sql (integration
test). Here we verify the application-layer guarantees that hold without DB.
"""

from __future__ import annotations

from app.core.audit_middleware import AUDIT_EXCLUDED_PREFIXES, SENSITIVE_KEYS, _redact


def test_redact_top_level_sensitive_keys():
    data = {"password": "s3cret", "name": "ok"}
    out = _redact(data)
    assert out["password"] == "***"
    assert out["name"] == "ok"


def test_redact_recursive_nested():
    data = {"user": {"secret": "x", "keep": 1}, "items": [{"refresh_token": "abc", "k": 2}]}
    out = _redact(data)
    assert out["user"]["secret"] == "***"
    assert out["user"]["keep"] == 1
    assert out["items"][0]["refresh_token"] == "***"
    assert out["items"][0]["k"] == 2


def test_redact_none_and_empty():
    assert _redact(None) is None
    assert _redact({}) == {}


def test_sensitive_keys_cover_credentials():
    for key in ("password", "old_password", "new_password", "refresh_token", "access_token",
                "secret", "secret_enc", "key_enc"):
        assert key in SENSITIVE_KEYS


def test_excluded_prefixes_cover_docs_and_ws():
    assert "/docs" in AUDIT_EXCLUDED_PREFIXES
    assert "/openapi.json" in AUDIT_EXCLUDED_PREFIXES
    assert "/ws/exec" in AUDIT_EXCLUDED_PREFIXES
    assert "/agent/ws" in AUDIT_EXCLUDED_PREFIXES
