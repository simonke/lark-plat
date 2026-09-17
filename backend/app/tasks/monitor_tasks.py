"""Celery tasks: monitor alert sweep (P2-MA B1 time trigger).

Pure event-driven evaluation has no clock, so "sustained condition -> firing" and
"sustained un-recovered -> escalation" need a periodic sweep. This reuses the
existing rule-engine helpers (no duplicated logic).
"""

from __future__ import annotations

import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _new_session():
    from app.db.session import SessionLocal

    return SessionLocal()


@celery_app.task(name="app.tasks.monitor_tasks.monitor_alert_sweep")
def monitor_alert_sweep() -> dict:
    from app.services import monitor_service

    db = _new_session()
    try:
        result = monitor_service.sweep_active_alerts(db)
        logger.info("monitor: alert sweep %s", result)
        return result
    finally:
        db.close()
