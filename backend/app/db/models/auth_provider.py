"""P2-3 identity providers (LDAP / OAuth2 SSO).

Add-only, per api-design-v3 §3 + architecture-phase23 §5. Secrets live in
`config_enc` (AES-GCM, same envelope as notify_channel.config_enc); the read
side masks them. `code` is the routing key used by
`/auth/oauth/{provider}/*` and the login-page provider list.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

AUTH_PROVIDER_TYPES = ("ldap", "oauth2")
AUTH_SOURCES = ("local", "ldap", "oauth2")


class AuthProvider(Base, TimestampMixin):
    __tablename__ = "auth_provider"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ldap/oauth2
    config_enc: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )  # JSON, AES-GCM
    enabled: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
