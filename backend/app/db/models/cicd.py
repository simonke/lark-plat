"""CI/CD integration models (P3-5): providers + release orchestration (add-only).

``cicd_provider`` registers an external CI/CD system (gitlab / jenkins / generic);
its secrets live **per-value AES-GCM encrypted** in ``config_enc`` and are never
echoed in plaintext. ``release`` records one delivery orchestration. Per the
@架构 P3-5 tuple v1.0 (§14) a release REUSES the §13 workflow engine
(``release == 1 workflow_run`` with ``trigger_type='release'``) instead of
re-implementing an orchestrator.

Frozen contract: @架构 P3-5 tuple v1.0 (seq3043) + design §14.
Add-only; single head descending from the P3-4 rev ``a1b2c3d4e5f7``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Frozen vocabularies (tuple seq3043 == design §14).
CICD_PROVIDER_TYPES = ("gitlab", "jenkins", "generic")
CICD_PROVIDER_STATUSES = ("unknown", "ok", "error")
RELEASE_ENVS = ("dev", "test", "prod")
# pending->deploying->canary->succeeded / failed->rolled_back / terminal cancelled.
RELEASE_STATUSES = (
    "pending",
    "deploying",
    "canary",
    "succeeded",
    "failed",
    "rolled_back",
    "cancelled",
)
RELEASE_TERMINAL_STATUSES = ("succeeded", "failed", "rolled_back", "cancelled")


class CicdProvider(Base, TimestampMixin):
    """A registered external CI/CD provider; ``config_enc`` holds per-value ciphertext."""

    __tablename__ = "cicd_provider"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    config_enc: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Release(Base, TimestampMixin):
    """One release orchestration; ``workflow_run_id`` links the reused §13 run."""

    __tablename__ = "release"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cicd_provider.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    app: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    env: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    workflow_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_host_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rolled_back_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
