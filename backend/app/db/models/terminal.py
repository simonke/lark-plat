"""Terminal session and recording models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class TerminalSession(Base, TimestampMixin):
    __tablename__ = "terminal_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    host_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset_host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False, index=True)
    # open/awaiting_approval/closed
    close_reason: Mapped[str] = mapped_column(String(32), default="")
    terminated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sensitive: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_out: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_in: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    __table_args__ = (
        Index("ix_terminal_host_status", "host_id", "status"),
        Index("ix_terminal_user_status", "user_id", "status"),
    )


class TerminalRecordingChunk(Base, TimestampMixin):
    __tablename__ = "terminal_recording_chunk"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("terminal_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data_enc: Mapped[str] = mapped_column(Text, nullable=False)  # AES-GCM

    __table_args__ = (UniqueConstraint("session_id", "offset"),)
