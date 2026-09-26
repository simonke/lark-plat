"""P6 (AIOps E6) governed automation models.

Add-only, single head migration `P6_REV`; four NEW tables. `remediation_run` is
deliberately NOT created — a remediation run is an existing `workflow_run`. The
new columns are plain `String` with comment enums (no CHECK/Enum, so the models
layer never imports from the services layer).

Frozen contract: @架构 P6 tuple r1 (seq3560 + notes r1.1-r1.7) + @需求 §30.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AutomationWhitelist(Base, TimestampMixin):
    """Governed whitelist: only `low` risk within the whitelist may auto (L4)."""

    __tablename__ = "automation_whitelist"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)  # RISK_LEVELS
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class RemediationPolicy(Base, TimestampMixin):
    """Governed policy: `asset_class x op_type -> level / whitelist / verification /
    threshold / rollback window`."""

    __tablename__ = "remediation_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_class: Mapped[str] = mapped_column(String(64), nullable=False)
    op_type: Mapped[str] = mapped_column(String(64), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # L0..L4
    whitelist_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    verification_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    circuit_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rollback_window: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AutomationLevel(Base, TimestampMixin):
    """Governed automation level matrix (L0..L4 capability/authorization)."""

    __tablename__ = "automation_level"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)  # L0..L4
    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CircuitBreakerState(Base, TimestampMixin):
    """Governed circuit-breaker state (`closed -> open -> half -> closed`)."""

    __tablename__ = "circuit_breaker_state"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(16), default="closed", nullable=False)
    current: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_tripped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
