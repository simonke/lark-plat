"""Pydantic schemas - exec, script, schedule, approval, notify, dashboard."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- exec


class ExecTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = "command"  # command/script
    script_id: int | None = None
    script_version: int | None = None
    command: str | None = None
    params: dict | None = None
    target_host_ids: list[int] = Field(min_length=1)
    mode: str = "batch"
    timeout_sec: int = Field(default=300, ge=1, le=86400)
    retry: int = Field(default=0, ge=0, le=10)


class ExecTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_no: str
    name: str
    kind: str
    script_id: int | None
    script_version: int | None
    command: str | None
    params: dict | None
    target_host_ids: dict | None
    mode: str
    timeout_sec: int
    retry: int
    sensitive_flag: int
    approve_required: int
    approval_id: int | None
    status: str
    created_by: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class ExecTaskDetail(ExecTaskOut):
    hosts: list["ExecHostOut"] = []
    approval_status: str | None = None


class ExecHostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    host_id: int
    hostname: str
    ip: str
    executor: str
    status: str
    exit_code: int | None
    started_at: datetime | None
    finished_at: datetime | None


class ExecLogOut(BaseModel):
    seq: int
    level: str
    content: str
    created_at: datetime


class ExecLogPage(BaseModel):
    list: list[ExecLogOut]
    next_seq: int


class ExecStats(BaseModel):
    total: int = 0
    pending: int = 0
    running: int = 0
    success: int = 0
    failed: int = 0
    timed_out: int = 0
    canceled: int = 0


# ---------------------------------------------------------------- script


class ScriptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    type: str = "shell"
    content: str = Field(min_length=1)
    params_def: dict | None = None
    remark: str = ""


class ScriptUpdate(BaseModel):
    content: str | None = None
    params_def: dict | None = None
    change_log: str = ""
    remark: str | None = None


class ScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    current_version: int
    params_def: dict | None
    remark: str
    created_by: int | None
    created_at: datetime


class ScriptDetail(ScriptOut):
    content: str = ""


class ScriptVersionOut(BaseModel):
    id: int
    script_id: int
    version: int
    content: str
    params_def: dict | None
    change_log: str
    created_by: int | None
    created_at: datetime


class RollbackIn(BaseModel):
    version: int = Field(ge=1)


class ScriptTestIn(BaseModel):
    params: dict | None = None


# ---------------------------------------------------------------- schedule


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = "command"
    script_id: int | None = None
    command: str | None = None
    params: dict | None = None
    trigger_type: str = "cron"  # cron/interval
    cron_expr: str | None = None
    timezone: str = "Asia/Shanghai"
    interval_sec: int | None = None
    target_host_ids: list[int] = Field(min_length=1)
    timeout_sec: int = Field(default=300, ge=1)
    retry: int = Field(default=0, ge=0, le=10)
    concurrency_limit: int = Field(default=10, ge=1, le=100)
    enabled: int = 1


class ScheduleUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    script_id: int | None = None
    command: str | None = None
    params: dict | None = None
    trigger_type: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    interval_sec: int | None = None
    target_host_ids: list[int] | None = None
    timeout_sec: int | None = None
    retry: int | None = None
    concurrency_limit: int | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    script_id: int | None
    command: str | None
    params: dict | None
    trigger_type: str
    cron_expr: str | None
    timezone: str
    interval_sec: int | None
    target_host_ids: dict | None
    timeout_sec: int
    retry: int
    concurrency_limit: int
    enabled: int
    created_by: int | None
    created_at: datetime


class ScheduleStatusIn(BaseModel):
    enabled: int = Field(ge=0, le=1)


class ScheduleRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    schedule_task_id: int
    run_no: str
    status: str
    task_id: int | None
    started_at: datetime
    finished_at: datetime | None
    error_msg: str | None


# ---------------------------------------------------------------- approval


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    request_no: str
    biz_type: str
    biz_id: int
    title: str
    reason: str
    requester_id: int
    sensitive_hit: str
    status: str
    approver_id: int | None
    decided_at: datetime | None
    created_at: datetime
    version: int


class ApprovalDetail(ApprovalOut):
    timeline: list["ApprovalRecordOut"] = []


class ApprovalRecordOut(BaseModel):
    action: str
    operator_id: int
    comment: str
    created_at: datetime


class ApproveIn(BaseModel):
    comment: str = ""


class RuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = "keyword"  # keyword/count
    value: dict
    enabled: int = 1


class RuleUpdate(BaseModel):
    name: str | None = None
    value: dict | None = None
    enabled: int | None = None


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    value: dict
    enabled: int
    created_at: datetime


# ---------------------------------------------------------------- notify


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=16)
    config: dict
    enabled: int = 1


class ChannelUpdate(BaseModel):
    name: str | None = None
    config: dict | None = None
    enabled: int | None = None


class ChannelOut(BaseModel):
    id: int
    name: str
    type: str
    enabled: int
    config_mask: dict
    created_at: datetime


class ChannelTestIn(BaseModel):
    title: str = "test"
    content: str = "lark-plat test message"


class NotifyRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    channel_id: int | None
    scene: str
    target: str
    title: str
    content: str
    status: str
    error_msg: str | None
    sent_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------- dashboard


class DashboardStats(BaseModel):
    host_total: int
    host_online: int
    tasks_running: int
    today_tasks: int
    today_success: int
    pending_approvals: int


class TrendPoint(BaseModel):
    date: str
    total: int
    success: int
    failed: int


class RecentTask(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_no: str
    name: str
    status: str
    kind: str
    created_at: datetime


class RecentApproval(BaseModel):
    id: int
    request_no: str
    title: str
    status: str
    created_at: datetime
