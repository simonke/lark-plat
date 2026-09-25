"""Workflow / Playbook models (P3-4): DAG definition + run state machine.

Playbook = a versioned DAG. ``Workflow`` holds the ``current_version`` pointer;
``WorkflowVersion`` is append-only (a new version per edit, rollback = move the
pointer); ``WorkflowRun``/``WorkflowNodeRun`` record execution state. Node types
reuse the一期 exec_task / approval primitives — this module does NOT copy their
logic.

Frozen contract: @架构 P3-4 tuple (seq2894) + design §13 (`architecture-phase23.md`).
Add-only; single head descending from the P3-3 head ``f2a3b4c5d6e7``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# Frozen vocabularies (tuple seq2894 == design §13.2).
NODE_TYPES = ("exec_task", "manual_approval", "wait", "callback", "sleep")
RUN_STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")
NODE_STATUSES = ("pending", "running", "succeeded", "failed", "skipped", "waiting")
TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled")
TRIGGER_TYPES = ("manual", "ticket", "schedule", "alert", "release")


class Workflow(Base, TimestampMixin):
    """Versioned Playbook header; ``current_version`` points at the live version."""

    __tablename__ = "workflow"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(512), default="")
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class WorkflowVersion(Base, TimestampMixin):
    """Append-only DAG definition snapshot (UNIQUE(workflow_id, version))."""

    __tablename__ = "workflow_version"
    __table_args__ = (UniqueConstraint("workflow_id", "version", name="uq_workflow_version"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    editor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class WorkflowRun(Base, TimestampMixin):
    """One execution of a workflow version; status ∈ RUN_STATUSES."""

    __tablename__ = "workflow_run"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workflow.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
    trigger_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class WorkflowNodeRun(Base, TimestampMixin):
    """Per-node execution record (UNIQUE(run_id, node_key))."""

    __tablename__ = "workflow_node_run"
    __table_args__ = (UniqueConstraint("run_id", "node_key", name="uq_workflow_node_run"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workflow_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    exec_task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approval_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
