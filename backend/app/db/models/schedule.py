"""Schedule (cron) models and approval workflow models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ScheduleTask(Base, TimestampMixin):
    __tablename__ = "schedule_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="command")  # command/script
    script_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("script.id"), nullable=True)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(16), nullable=False)  # cron/interval
    cron_expr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    interval_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_host_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timeout_sec: Mapped[int] = mapped_column(Integer, default=300)
    retry: Mapped[int] = mapped_column(Integer, default=0)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=10)
    enabled: Mapped[int] = mapped_column(Integer, default=1, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ScheduleRun(Base, TimestampMixin):
    __tablename__ = "schedule_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    schedule_task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("schedule_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running/success/failed/partial
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)


class ApprovalRequest(Base, TimestampMixin):
    __tablename__ = "approval_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    biz_type: Mapped[str] = mapped_column(String(16), default="exec")
    biz_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)  # exec_task.id
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    requester_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    sensitive_hit: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending/approved/rejected/canceled
    approver_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ApprovalRule(Base, TimestampMixin):
    __tablename__ = "approval_rule"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # keyword/count
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=False)  # {"word": "rm -rf"} or {"threshold": 50}
    trigger_action: Mapped[str] = mapped_column(String(16), default="create")
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class ApprovalRecord(Base, TimestampMixin):
    __tablename__ = "approval_record"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    approval_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("approval_request.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # submit/approve/reject/cancel
    operator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    comment: Mapped[str] = mapped_column(String(512), default="")
