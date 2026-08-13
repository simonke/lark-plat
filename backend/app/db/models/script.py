"""Script library models (versioned)."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Script(Base, TimestampMixin):
    __tablename__ = "script"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), default="shell")  # shell/powershell/python
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    params_def: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    remark: Mapped[str] = mapped_column(String(256), default="")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ScriptVersion(Base, TimestampMixin):
    __tablename__ = "script_version"
    __table_args__ = (UniqueConstraint("script_id", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("script.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    params_def: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    change_log: Mapped[str] = mapped_column(String(512), default="")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
