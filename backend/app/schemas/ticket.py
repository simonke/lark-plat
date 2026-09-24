"""Ticket (工单 P3-1) request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    category: str = "incident"  # incident/change/request/other
    priority: str = "medium"  # low/medium/high/urgent
    description: str = ""
    assignee_id: int | None = None
    host_ids: list[int] | None = None
    due_at: datetime | None = None


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    category: str | None = None
    priority: str | None = None
    description: str | None = None
    assignee_id: int | None = None
    due_at: datetime | None = None


class TicketAssignIn(BaseModel):
    assignee_id: int = Field(ge=1)


class TicketDoneIn(BaseModel):
    remark: str = ""
    exec_task_id: int | None = Field(default=None, ge=1)


class TicketCommentIn(BaseModel):
    content: str = Field(min_length=1)


class TicketRefIn(BaseModel):
    ref_type: str = Field(min_length=1, max_length=16)
    ref_id: int = Field(ge=1)


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_no: str
    title: str
    category: str
    priority: str
    status: str
    requester_id: int | None
    assignee_id: int | None
    team_id: int | None
    description: str
    sla_due_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    version: int
    created_at: datetime


class TicketRefOut(BaseModel):
    id: int
    ref_type: str
    ref_id: int


class TicketCommentOut(BaseModel):
    id: int
    author_id: int | None
    content: str
    created_at: datetime | None = None


class TicketAttachmentOut(BaseModel):
    id: int
    file_id: int
    filename: str
    size: int
    created_at: datetime | None = None


class TicketDetail(TicketOut):
    refs: list[TicketRefOut] = []
    comments: list[TicketCommentOut] = []
    attachments: list[TicketAttachmentOut] = []
