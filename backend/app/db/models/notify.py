"""Notify, audit and global config models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class NotifyChannel(Base, TimestampMixin):
    __tablename__ = "notify_channel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # lark/email/dingtalk/wecom/webhook
    config_enc: Mapped[str] = mapped_column(Text, nullable=False)  # JSON, AES-GCM encrypted
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class NotifyRecord(Base, TimestampMixin):
    __tablename__ = "notify_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    scene: Mapped[str] = mapped_column(String(16), default="exec")  # exec/schedule/approval/test
    target: Mapped[str] = mapped_column(String(256), default="")
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="sent")  # sent/failed
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only audit log. Application layer only INSERT; DB layer revokes UPDATE/DELETE."""

    __tablename__ = "sys_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    module: Mapped[str] = mapped_column(String(32), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), default="", index=True)
    method: Mapped[str] = mapped_column(String(8), default="")
    path: Mapped[str] = mapped_column(String(256), default="")
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[int] = mapped_column(Integer, default=1)
    cost_ms: Mapped[int] = mapped_column(Integer, default=0)
    trace_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class ConfigRule(Base, TimestampMixin):
    """Global config: sensitive words, batch threshold, concurrency limits..."""

    __tablename__ = "config_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    rule_value: Mapped[dict | None] = mapped_column(JSONB, nullable=False)
    remark: Mapped[str] = mapped_column(String(256), default="")
