"""Dashboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=Result)
def stats(db: DbDep, user: UserDep):
    user.require_perm("dashboard:view")
    return Result.ok(dashboard_service.stats(db, user))


@router.get("/task-trend", response_model=Result)
def task_trend(db: DbDep, user: UserDep, days: int = Query(default=7, ge=1, le=90)):
    user.require_perm("dashboard:view")
    return Result.ok(dashboard_service.task_trend(db, user, days))


@router.get("/recent-tasks", response_model=Result)
def recent_tasks(db: DbDep, user: UserDep):
    user.require_perm("dashboard:view")
    return Result.ok(dashboard_service.recent_tasks(db, user))


@router.get("/recent-approvals", response_model=Result)
def recent_approvals(db: DbDep, user: UserDep):
    user.require_perm("dashboard:view")
    return Result.ok(dashboard_service.recent_approvals(db, user))
