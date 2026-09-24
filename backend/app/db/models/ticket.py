"""Ticket (工单) models - Phase 3 P3-1, add-only.

Frozen contract (architecture-phase23 §7 + api-design-v3 §5):
  ticket             - ticket lifecycle (create/assign/accept/processing/done/close/cancel)
  ticket_comment     - append-only comments
  ticket_attachment  - attachment pointing at a file_package (soft ref, no physical delete)
  ticket_ref         - polymorphic reference to exec_task/approval/asset_host/schedule/kb_article/script

Ownership FKs point at sys_user (one-phase table). Enums live here (not in the
service) per @架构 seq2605: only the transition map lives in the service.
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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Lifecycle states (reopen is an action, not a state).
TICKET_STATUSES = ("create", "assign", "accept", "processing", "done", "close", "cancel")
# Editing is allowed only before acceptance.
TICKET_EDITABLE_STATUSES = ("create", "assign")
TICKET_CATEGORIES = ("incident", "change", "request", "other")
TICKET_PRIORITIES = ("low", "medium", "high", "urgent")
# Membership is the frozen contract (seq2608 union); order is NOT.
TICKET_REF_TYPES = ("exec_task", "approval", "asset_host", "schedule", "kb_article", "script")


class Ticket(Base, TimestampMixin):
    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Human-readable business key, frozen at create time (P3.x). Mirrors ExecTask/TransferTask
    # task_no: String(32) unique/not-null/index; generated race-free from seq_ticket_no.
    ticket_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str] = mapped_column(String(16), default="incident", nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="create", nullable=False, index=True)
    requester_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, index=True
    )
    assignee_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("sys_user.id"), nullable=True, index=True
    )
    team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_ticket_requester_status", "requester_id", "status"),
        Index("ix_ticket_assignee_status", "assignee_id", "status"),
    )


class TicketComment(Base):
    """Append-only comment (no updated_at)."""

    __tablename__ = "ticket_comment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketAttachment(Base):
    """Attachment soft-referencing a file_package row (no FK / no physical delete)."""

    __tablename__ = "ticket_attachment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(256), default="")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TicketRef(Base):
    """Polymorphic reference: (ticket_id, ref_type, ref_id) is unique/idempotent."""

    __tablename__ = "ticket_ref"
    __table_args__ = (UniqueConstraint("ticket_id", "ref_type", "ref_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
