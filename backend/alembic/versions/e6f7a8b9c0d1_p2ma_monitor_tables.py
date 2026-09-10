"""p2-ma: monitoring & alerting tables (add-only)

Phase-2 P2-MA frozen contract (2026-09-09):
  mon_metric_sample         - time-series metric samples (entity model, fingerprint)
  mon_metric_daily          - daily down-sampled aggregation
  mon_adapter               - adapters (type/name/endpoint/config/health)
  mon_event_inbox           - normalized MonEvent inbound, pre-rule-eval, dead-letter
  mon_rule                  - alert rules (condition_operator/threshold/duration/cooldown/escalation)
  mon_alert                 - alert lifecycle pending/firing/acknowledged/resolved (CAS version)
  mon_alert_event_log       - append-only event trail (fire/acknowledge/escalate/resolve/suppress)

All tables are new; a single alembic head is preserved. ownership/operator FKs -> sys_user.

Revision ID: e6f7a8b9c0d1
Revises: f5e010c0a100
Create Date: 2026-09-09 20:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e6f7a8b9c0d1"
down_revision = "f5e010c0a100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── mon_metric_sample ──────────────────────────────────────────────
    op.create_table(
        "mon_metric_sample",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("entity_name", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mon_metric_sample_source", "mon_metric_sample", ["source"])
    op.create_index("ix_mon_metric_sample_metric_name", "mon_metric_sample", ["metric_name"])
    op.create_index("ix_mon_metric_sample_entity_id", "mon_metric_sample", ["entity_id"])
    op.create_index("ix_mon_metric_sample_fingerprint", "mon_metric_sample", ["fingerprint"])
    op.create_index("ix_mon_metric_sample_ts", "mon_metric_sample", ["ts"])
    op.create_index(
        "ix_mon_metric_sample_source_entity_ts",
        "mon_metric_sample",
        ["source", "entity_id", "ts"],
    )
    op.create_index(
        "ix_mon_metric_sample_metric_ts",
        "mon_metric_sample",
        ["metric_name", "ts"],
    )

    # ── mon_metric_daily ───────────────────────────────────────────────
    op.create_table(
        "mon_metric_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("min_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "metric_name", "entity_id", "day"),
    )
    op.create_index("ix_mon_metric_daily_entity_id", "mon_metric_daily", ["entity_id"])
    op.create_index("ix_mon_metric_daily_day", "mon_metric_daily", ["day"])

    # ── mon_adapter ────────────────────────────────────────────────────
    op.create_table(
        "mon_adapter",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="healthy"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics_received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_mon_adapter_type", "mon_adapter", ["type"])
    op.create_index("ix_mon_adapter_status", "mon_adapter", ["status"])

    # ── mon_event_inbox ────────────────────────────────────────────────
    op.create_table(
        "mon_event_inbox",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("entity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("labels", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("event_key", sa.String(length=96), nullable=True),
        sa.Column("mapping_warning", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mon_event_inbox_source", "mon_event_inbox", ["source"])
    op.create_index("ix_mon_event_inbox_kind", "mon_event_inbox", ["kind"])
    op.create_index("ix_mon_event_inbox_ts", "mon_event_inbox", ["ts"])
    op.create_index("ix_mon_event_inbox_fingerprint", "mon_event_inbox", ["fingerprint"])
    op.create_index("ix_mon_event_inbox_event_key", "mon_event_inbox", ["event_key"])
    op.create_index("ix_mon_event_inbox_status", "mon_event_inbox", ["status"])

    # ── mon_rule ───────────────────────────────────────────────────────
    op.create_table(
        "mon_rule",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_source", sa.String(length=16), nullable=True),
        sa.Column("event_kind", sa.String(length=16), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=True),
        sa.Column("condition_operator", sa.String(length=2), nullable=False),
        sa.Column("condition_threshold", sa.Float(), nullable=False),
        sa.Column("condition_duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("escalation_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("escalation_after_seconds", sa.Integer(), nullable=True),
        sa.Column("escalation_severity", sa.String(length=16), nullable=True),
        sa.Column("notify_scene", sa.String(length=16), nullable=False, server_default="alert"),
        sa.Column("notify_channel_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mon_rule_name", "mon_rule", ["name"])
    op.create_index("ix_mon_rule_enabled", "mon_rule", ["enabled"])
    op.create_index("ix_mon_rule_deleted", "mon_rule", ["deleted"])
    op.create_index("ix_mon_rule_created_by", "mon_rule", ["created_by"])

    # ── mon_alert ──────────────────────────────────────────────────────
    op.create_table(
        "mon_alert",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.BigInteger(), nullable=True),
        sa.Column("rule_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("entity", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="agent"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="warning"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("last_value", sa.Float(), nullable=True),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("event_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mon_alert_rule_id", "mon_alert", ["rule_id"])
    op.create_index("ix_mon_alert_status", "mon_alert", ["status"])
    op.create_index("ix_mon_alert_severity", "mon_alert", ["severity"])
    op.create_index("ix_mon_alert_fingerprint", "mon_alert", ["fingerprint"])

    # ── mon_alert_event_log ────────────────────────────────────────────
    op.create_table(
        "mon_alert_event_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("from_status", sa.String(length=16), nullable=True),
        sa.Column("to_status", sa.String(length=16), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["mon_alert.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mon_alert_event_log_alert_at",
        "mon_alert_event_log",
        ["alert_id", "at"],
    )
    op.create_index("ix_mon_alert_event_log_operator_id", "mon_alert_event_log", ["operator_id"])


def downgrade() -> None:
    op.drop_table("mon_alert_event_log")
    op.drop_table("mon_alert")
    op.drop_table("mon_rule")
    op.drop_table("mon_event_inbox")
    op.drop_table("mon_adapter")
    op.drop_table("mon_metric_daily")
    op.drop_table("mon_metric_sample")
