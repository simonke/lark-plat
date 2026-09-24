"""Knowledge base (知识库) models - Phase 3 P3-2, add-only.

Frozen contract (architecture-phase23 §8 + api-design-v3 §6):
  kb_article         - article metadata (current_version pointer)
  kb_article_version - append-only version rows (script-version semantics)
  kb_category        - self-referencing category tree (parent_id, 0 = root)
  kb_article_tag     - article tag rows (unique per article)

Version rows are append-only: edit and rollback both append a new version and
move kb_article.current_version forward; existing version rows are never mutated.
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

KB_VISIBILITIES = ("public", "internal", "classified")


class KbCategory(Base, TimestampMixin):
    __tablename__ = "kb_category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)

    __table_args__ = (Index("ix_kb_category_parent_sort", "parent_id", "sort"),)


class KbArticle(Base, TimestampMixin):
    __tablename__ = "kb_article"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="internal", nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    author_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    summary: Mapped[str] = mapped_column(String(512), default="")


class KbArticleVersion(Base):
    """Append-only article version snapshot."""

    __tablename__ = "kb_article_version"
    __table_args__ = (UniqueConstraint("article_id", "version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_article.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    change_log: Mapped[str] = mapped_column(String(256), default="")
    editor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("sys_user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KbArticleTag(Base):
    __tablename__ = "kb_article_tag"
    __table_args__ = (UniqueConstraint("article_id", "tag"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kb_article.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
