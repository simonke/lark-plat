"""Worker task-registration guard (defect 5f6d0a9 / D-celery-1).

Regression fix commit 5f6d0a9 added `imports=("app.tasks.exec_tasks",)` to
celery_app.conf so a worker started with `-A app.tasks.celery_app` actually
registers the exec dispatch and timeout-scan tasks. Before the fix the worker
registry only contained notify_send / trigger_schedules, so beat's
`scan-exec-timeouts` dispatch failed with unregistered-task and exec dispatch
silently never executed on the worker.

This guard simulates the worker load path (apply celery_app.conf.imports) and
pins the four task names that must be registered:
  exec_dispatch / scan_timeouts / notify_send / trigger_schedules
plus that every beat entry task resolves to a registered task.

Add-only single file; mirrors the external lock-test pattern.
"""

from __future__ import annotations

import importlib

from app.tasks.celery_app import celery_app

_REQUIRED = (
    "app.tasks.exec_tasks.exec_dispatch",
    "app.tasks.exec_tasks.scan_timeouts",
    "app.tasks.notify_tasks.notify_send",
    "app.tasks.schedule_tasks.trigger_schedules",
)


def _worker_registry():
    """Apply celery_app.conf.imports the way `celery worker` bootstraps tasks."""
    for module in celery_app.conf.imports:
        importlib.import_module(module)
    return set(celery_app.tasks.keys())


def test_worker_conf_imports_exec_tasks():
    assert "app.tasks.exec_tasks" in celery_app.conf.imports


def test_worker_registers_all_core_tasks():
    registry = _worker_registry()
    for name in _REQUIRED:
        assert name in registry


def test_beat_schedule_task_names_all_registered():
    registry = _worker_registry()
    for entry in celery_app.conf.beat_schedule.values():
        assert "task" in entry
        assert entry["task"] in registry