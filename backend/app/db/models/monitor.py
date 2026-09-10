"""Monitoring & alerting models (Phase 2 P2-MA, add-only).

Tables follow the one-phase `mon_*` prefix convention (frozen contract 2026-09-09):
  mon_metric_sample / mon_metric_daily   - time-series samples + daily aggregation
  mon_adapter                            - external/self-collection adapter
  mon_event_inbox                        - normalized MonEvent inbound (pre-eval)
  mon_rule                               - alert rules (threshold based)
  mon_alert                              - alert lifecycle: pending/firing/acknowledged/resolved
  mon_alert_event_log                    - append-only alert event trail (fire/acknowledge/escalate/resolve/suppress)
Ownership/operator FKs point at sys_user (one-phase table), created_by too.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin

MON_SOURCES = ("agent", "prometheus", "elk", "skywalking")
MON_KINDS = ("metric", "alert", "log", "apm")
MON_ADAPTER_TYPES = ("prometheus", "elk", "skywalking")
MON_LEVELS = ("info", "warning", "critical")
MON_RULE_OPS = (">", "<", ">=", "<=", "==", "!=")
MON_ALERT_STATUSES = ("pending", "firing", "acknowledged", "resolved")
MON_ALERT_ACTIONS = ("fire", "acknowledge", "escalate", "resolve", "suppress")
MON_EVENT_STATUSES = ("pending", "processed", "dead_letter")
MON_ADAPTER_STATUSES = ("healthy", "degraded", "disconnected", "dead")
MON_NOTIFY_SCENES = ("alert", "exec", "schedule")


# ---------------------------------------------------------------------------
# mon_metric_sample — per-metric raw sample (append-only, high volume)
# ---------------------------------------------------------------------------

class MonMetricSample(Base):
    __tablename__ = "mon_metric_sample"
    __table_args__ = (
        Index("ix_mon_metric_sample_source_entity_ts", "source", "entity_id", "ts"),
        Index("ix_mon_metric_sample_metric_ts", "metric_name", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # host|app|service
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(256), default="")
    value: Mapped[float] = mapped_column(Float, nullable=False)
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# mon_metric_daily — pre-aggregated daily rollup (query fast-path)
# ---------------------------------------------------------------------------

class MonMetricDaily(Base):
    __tablename__ = "mon_metric_daily"
    __table_args__ = (UniqueConstraint("source", "metric_name", "entity_id", "day"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    min_value: Mapped[float] = mapped_column(Float, default=0)
    max_value: Mapped[float] = mapped_column(Float, default=0)
    avg_value: Mapped[float] = mapped_column(Float, default=0)
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# mon_adapter — data source adapter registry & health
# ---------------------------------------------------------------------------

class MonAdapter(Base, TimestampMixin):
    __tablename__ = "mon_adapter"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # prometheus|elk|skywalking
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(256), default="")
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="healthy", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics_received_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)


# ---------------------------------------------------------------------------
# mon_event_inbox — normalized MonEvent inbound (pre-eval, dead-letter)
# ---------------------------------------------------------------------------

class MonEventInbox(Base):
    __tablename__ = "mon_event_inbox"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    entity: Mapped[dict] = mapped_column(JSONB, default=dict)  # {entity_type, entity_id, entity_name}
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    event_key: Mapped[str | None] = mapped_column(String(96), nullable=True, index=True)
    mapping_warning: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# mon_rule — alert rule definition
# ---------------------------------------------------------------------------

class MonRule(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "mon_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)

    # Event filter
    event_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # null = all sources
    event_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # metric|alert|log|apm
    metric_name: Mapped[str | None] = mapped_column(String(128), nullable=True)  # required when kind=metric

    # Condition
    condition_operator: Mapped[str] = mapped_column(String(2), nullable=False)  # >,<,>=,<=,==,!=
    condition_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    condition_duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Scope (US-03: server-side entity filtering)
    scope_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # host|app|service|null=all
    scope_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {ids: [entity_ids]}

    # Severity level for alerts created by this rule
    level: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)

    # Cooldown / convergence
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    converge_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # convergence dedup window

    # Escalation
    escalation_enabled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalation_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    escalate_levels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {ids: ["warning","critical"]}

    # Notification
    notify_scene: Mapped[str] = mapped_column(String(16), default="alert", nullable=False)
    notify_channel_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {ids: [channel_id]}

    # Ownership
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)


# ---------------------------------------------------------------------------
# mon_alert — active alert state (4 main states + suppressed transient)
# ---------------------------------------------------------------------------

class MonAlert(Base, TimestampMixin):
    __tablename__ = "mon_alert"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    rule_name: Mapped[str] = mapped_column(String(128), default="")

    # Entity (JSONB for flexibility, matches MonEventInbox.entity shape)
    entity: Mapped[dict] = mapped_column(JSONB, default=dict)  # {entity_type, entity_id, entity_name}

    # Alert state
    source: Mapped[str] = mapped_column(String(16), default="agent")
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="warning", nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)

    # Values
    last_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    fired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # CAS optimistic lock (concurrent state transitions)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Snapshot of the triggering event (for display / audit)
    event_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


# ---------------------------------------------------------------------------
# mon_alert_event_log — append-only state transition audit trail
# ---------------------------------------------------------------------------

class MonAlertEventLog(Base):
    __tablename__ = "mon_alert_event_log"
    __table_args__ = (Index("ix_mon_alert_event_log_alert_at", "alert_id", "at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("mon_alert.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # fire|acknowledge|escalate|resolve|suppress
    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
