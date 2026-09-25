"""Celery beat backstop for P3-4b workflow runs (engine tuple F, seq2918).

The in-process driver owns normal advancement; this sweep re-ticks non-terminal
runs so a node timeout still converges if a driver thread is lost.
"""

from __future__ import annotations

from app.tasks.celery_app import celery_app


def _new_session():
    from app.db.session import SessionLocal

    return SessionLocal()


@celery_app.task(name="app.tasks.workflow_tasks.scan_workflow_timeouts")
def scan_workflow_timeouts() -> int:
    from app.services import workflow_engine

    db = _new_session()
    try:
        return workflow_engine.scan_timeouts(db)
    finally:
        db.close()
