"""p3-1 + p3-2: ticket and knowledge-base tables (add-only, single head)

Phase-3 frozen contract (architecture-phase23 §7/§8 + api-design-v3 §5/§6):
  ticket             - ticket lifecycle (create/assign/accept/processing/done/close/cancel)
  ticket_comment     - append-only comments
  ticket_attachment  - attachment soft-referencing file_package (no FK / no physical delete)
  ticket_ref         - polymorphic ref (ticket_id, ref_type, ref_id) UNIQUE (idempotent)
  kb_article         - article metadata (current_version pointer)
  kb_article_version - append-only version rows
  kb_category        - self-referencing category tree (parent_id, 0 = root)
  kb_article_tag     - article tags (UNIQUE per article)

All tables are new and chained onto the P2 close-out head e8a1b2c3d4f5, keeping a
single alembic head. This migration belongs to allow-set C (forbidden on the shared
live DB) because it descends from the close-out migration; see
docs/migration-shared-db-allowlist.md.

Revision ID: c9e3f1a2b4d6
Revises: e8a1b2c3d4f5
Create Date: 2026-09-24 16:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9e3f1a2b4d6"
down_revision = "e8a1b2c3d4f5"
branch_labels = None
depends_on = None
# P3 descends from the P2 close-out => forbidden on the shared live DB.
SHARED_LIVE_DB_FORBIDDEN = True

_NOW = sa.text("now()")


def _ts(name: str, *, nullable: bool = False):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=_NOW, nullable=nullable)


def upgrade() -> None:
    # ── ticket ────────────────────────────────────────────────────────────
    op.create_table(
        "ticket",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="incident"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="create"),
        sa.Column("requester_id", sa.BigInteger(), nullable=True),
        sa.Column("assignee_id", sa.BigInteger(), nullable=True),
        sa.Column("team_id", sa.BigInteger(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["requester_id"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["assignee_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_status", "ticket", ["status"])
    op.create_index("ix_ticket_requester_id", "ticket", ["requester_id"])
    op.create_index("ix_ticket_assignee_id", "ticket", ["assignee_id"])
    op.create_index("ix_ticket_requester_status", "ticket", ["requester_id", "status"])
    op.create_index("ix_ticket_assignee_status", "ticket", ["assignee_id", "status"])

    # ── ticket_comment ────────────────────────────────────────────────────
    op.create_table(
        "ticket_comment",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_comment_ticket_id", "ticket_comment", ["ticket_id"])

    # ── ticket_attachment ─────────────────────────────────────────────────
    op.create_table(
        "ticket_attachment",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_attachment_ticket_id", "ticket_attachment", ["ticket_id"])
    op.create_index("ix_ticket_attachment_file_id", "ticket_attachment", ["file_id"])

    # ── ticket_ref ────────────────────────────────────────────────────────
    op.create_table(
        "ticket_ref",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("ref_type", sa.String(length=16), nullable=False),
        sa.Column("ref_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["ticket_id"], ["ticket.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_id", "ref_type", "ref_id"),
    )
    op.create_index("ix_ticket_ref_ticket_id", "ticket_ref", ["ticket_id"])
    op.create_index("ix_ticket_ref_ref_id", "ticket_ref", ["ref_id"])

    # ── kb_category ───────────────────────────────────────────────────────
    op.create_table(
        "kb_category",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_category_parent_id", "kb_category", ["parent_id"])
    op.create_index("ix_kb_category_parent_sort", "kb_category", ["parent_id", "sort"])

    # ── kb_article ────────────────────────────────────────────────────────
    op.create_table(
        "kb_article",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="internal"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("author_id", sa.BigInteger(), nullable=True),
        sa.Column("summary", sa.String(length=512), nullable=False, server_default=""),
        _ts("created_at"),
        _ts("updated_at"),
        sa.ForeignKeyConstraint(["author_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_kb_article_title", "kb_article", ["title"])
    op.create_index("ix_kb_article_category_id", "kb_article", ["category_id"])
    op.create_index("ix_kb_article_visibility", "kb_article", ["visibility"])

    # ── kb_article_version (append-only) ──────────────────────────────────
    op.create_table(
        "kb_article_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("change_log", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("editor_id", sa.BigInteger(), nullable=True),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["article_id"], ["kb_article.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["editor_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "version"),
    )
    op.create_index("ix_kb_article_version_article_id", "kb_article_version", ["article_id"])

    # ── kb_article_tag ────────────────────────────────────────────────────
    op.create_table(
        "kb_article_tag",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=False),
        _ts("created_at"),
        sa.ForeignKeyConstraint(["article_id"], ["kb_article.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "tag"),
    )
    op.create_index("ix_kb_article_tag_article_id", "kb_article_tag", ["article_id"])
    op.create_index("ix_kb_article_tag_tag", "kb_article_tag", ["tag"])


def downgrade() -> None:
    op.drop_table("kb_article_tag")
    op.drop_table("kb_article_version")
    op.drop_table("kb_article")
    op.drop_table("kb_category")
    op.drop_table("ticket_ref")
    op.drop_table("ticket_attachment")
    op.drop_table("ticket_comment")
    op.drop_table("ticket")
