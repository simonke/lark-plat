"""Security primitives: password hashing, JWT, AES-GCM credential encryption.

Reviewer red lines:
- passwords BCrypt-hashed
- JWT HS256, refresh token stored in Redis, logout blacklists access jti
- credentials AES-GCM encrypted with CREDENTIAL_ENCRYPT_KEY (env only), key_version reserved
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------- passwords


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------- JWT


def _jti() -> str:
    return uuid.uuid4().hex


def create_token(subject: str | int, token_type: str, expires_delta: timedelta, **extra: Any) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "jti": _jti(),
        "iat": now,
        "exp": now + expires_delta,
    }
    payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str | int, **extra: Any) -> str:
    return create_token(
        subject, "access", timedelta(minutes=settings.access_token_expire_minutes), **extra
    )


def create_refresh_token(subject: str | int) -> str:
    return create_token(subject, "refresh", timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError(f"invalid token: {exc}") from exc
    if expected_type and payload.get("type") != expected_type:
        raise ValueError("unexpected token type")
    return payload


# ------------------------------------------------------- credential (AES-GCM)


def _credential_key() -> bytes:
    raw = settings.credential_encrypt_key.encode()
    return hashlib.sha256(raw).digest()


def encrypt_secret(plain: str, key_version: int = 1) -> str:
    """Encrypt plaintext with AES-GCM. Returns base64(nonce + ciphertext + tag) prefixed v1."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    aesgcm = AESGCM(_credential_key())
    ct = aesgcm.encrypt(nonce, plain.encode(), None)
    blob = nonce + ct
    return f"v{key_version}:" + base64.b64encode(blob).decode()


def decrypt_secret(encrypted: str) -> str:
    """Decrypt an AES-GCM blob. key_version reserved for rotation."""
    if ":" not in encrypted:
        raise ValueError("bad credential format")
    version, payload = encrypted.split(":", 1)
    if not version.startswith("v"):
        raise ValueError("bad credential format")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = base64.b64decode(payload)
    nonce, ct = blob[:12], blob[12:]
    aesgcm = AESGCM(_credential_key())
    return aesgcm.decrypt(nonce, ct, None).decode()


def mask_secret(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        plain = decrypt_secret(encrypted)
    except Exception:
        return "***"
    if len(plain) <= 4:
        return "****"
    return plain[:2] + "*" * 6 + plain[-2:]
