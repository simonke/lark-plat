"""Celery app instance and beat schedule."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "lark_plat",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_track_started=True,
    worker_max_tasks_per_child=200,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "scan-exec-timeouts": {
        "task": "app.tasks.exec_tasks.scan_timeouts",
        "schedule": crontab(minute="*"),
    },
    "trigger-schedules": {
        "task": "app.tasks.schedule_tasks.trigger_schedules",
        "schedule": crontab(minute="*"),
    },
}
