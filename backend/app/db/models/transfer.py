"""File distribution models (Phase 2 P2-1, add-only).

Frozen contract (architecture-phase23 §3 + api-design-v3 §1):
  file_package    - uploaded file package (platform storage, sha256 manifest)
  file_item       - file inside a package (relative path, size, sha256, chunk_size)
  transfer_task   - push/pull task (state machine, per-target no)
  transfer_host   - task x host (per-host cursor/verify state machine)
  transfer_log    - per-host transfer log (exec_log-style monthly RANGE partitions)

Channels are resolved at dispatch time (AgentChannel default, SshChannel is an
interface placeholder in this batch). Ownership FKs -> sys_user (one-phase table).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

TRANSFER_MODES = ("push", "pull")
TRANSFER_CHANNELS = ("agent", "ssh", "degraded")

# per-host lifecycle: pending -> pulling/transferring -> verifying -> success | failed |
# verify_failed | degraded | canceled (retry moves failed/verify_failed/degraded back to pending).
TRANSFER_HOST_STATUSES = (
    "pending",
    "pulling",
    "transferring",
    "verifying",
    "success",
    "failed",
    "verify_failed",
    "degraded",
    "canceled",
)

# task lifecycle mirrors exec: processing -> success | partial | failed | canceled
TRANSFER_TASK_STATUSES = ("processing", "success", "partial", "failed", "canceled")


class FilePackage(Base, TimestampMixin):
    __tablename__ = "file_package"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), default="", index=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, default=0)
    store_path: Mapped[str] = mapped_column(String(512), nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)


class FileItem(Base):
    __tablename__ = "file_item"
    __table_args__ = (UniqueConstraint("package_id", "rel_path"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    package_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("file_package.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=1048576)


class TransferTask(Base, TimestampMixin):
    __tablename__ = "transfer_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)  # push/pull
    package_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("file_package.id"), nullable=True, index=True
    )
    source_host_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_host_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # pull source
    target_path: Mapped[str] = mapped_column(String(512), nullable=False)
    host_ids: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # {ids: [host_id]}
    overwrite: Mapped[int] = mapped_column(Integer, default=0)
    verify: Mapped[int] = mapped_column(Integer, default=1)  # sha256 verify per host
    limit_mbps: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0/None = unlimited
    status: Mapped[str] = mapped_column(String(16), default="processing", nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TransferHost(Base):
    __tablename__ = "transfer_host"
    __table_args__ = (UniqueConstraint("transfer_task_id", "host_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transfer_task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transfer_task.id", ondelete="CASCADE"), nullable=False, index=True
    )
    host_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    hostname: Mapped[str] = mapped_column(String(128), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    channel: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)  # agent/ssh/degraded
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    current_offset: Mapped[int] = mapped_column(BigInteger, default=0)
    verify_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TransferLog(Base):
    """Append-only per-host transfer log (exec_log partition pattern)."""

    __tablename__ = "transfer_log"
    __table_args__ = (
        UniqueConstraint("created_at", "transfer_host_id", "seq"),
        Index("ix_transfer_log_transfer_host_id", "transfer_host_id"),
        Index("ix_transfer_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transfer_host_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("transfer_host.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="info")  # info/error
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now(), nullable=False
    )