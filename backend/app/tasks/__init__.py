"""Celery tasks: notify sending and schedule triggering."""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import ConfigRule
from app.repositories import ConfigRuleRepository, ExecTaskRepository
from app.services import notify_service, schedule_service
from app.tasks.celery_app import celery_app


def _new_session():
    from app.db.session import SessionLocal

    return SessionLocal()


@celery_app.task(name="app.tasks.notify_tasks.notify_send")
def notify_send(channel_id: int, scene: str, target: str, title: str, content: str) -> dict:
    db = _new_session()
    try:
        return notify_service.send(db, channel_id, scene, target, title, content)
    finally:
        db.close()


@celery_app.task(name="app.tasks.schedule_tasks.trigger_schedules")
def trigger_schedules() -> int:
    """Beat entry: find due schedules and create exec tasks."""
    db = _new_session()
    try:
        return schedule_service.trigger_due(db)
    finally:
        db.close()
