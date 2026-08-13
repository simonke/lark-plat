"""Command execution models: exec_task state machine, exec_task_host, exec_log."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

EXEC_STATUSES = (
    "created",
    "awaiting_approval",
    "approved",
    "rejected",
    "running",
    "success",
    "failed",
    "partial",
    "canceled",
    "timed_out",
)

HOST_STATUSES = ("pending", "running", "success", "failed", "timed_out", "canceled")


class ExecTask(Base, TimestampMixin):
    __tablename__ = "exec_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="command")  # command/script
    script_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("script.id"), nullable=True)
    script_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    target_host_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # [ids]
    mode: Mapped[str] = mapped_column(String(16), default="batch")  # single/batch
    timeout_sec: Mapped[int] = mapped_column(Integer, default=300)
    retry: Mapped[int] = mapped_column(Integer, default=0)
    sensitive_flag: Mapped[int] = mapped_column(Integer, default=0)
    approve_required: Mapped[int] = mapped_column(Integer, default=0)
    approval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created", index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ExecTaskHost(Base, TimestampMixin):
    __tablename__ = "exec_task_host"
    __table_args__ = (UniqueConstraint("exec_task_id", "host_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    exec_task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exec_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(128), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    executor: Mapped[str] = mapped_column(String(16), default="agent")  # agent/ssh
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecLog(Base):
    __tablename__ = "exec_log"
    __table_args__ = (UniqueConstraint("task_host_id", "seq"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_host_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("exec_task_host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info/error
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
