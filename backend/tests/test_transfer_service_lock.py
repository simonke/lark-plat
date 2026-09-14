"""P2-1 transfer contract locks (rulings 2026-09-13).

Pins the architect's stats/aggregation rulings:
  - _stats folds pulling -> transferring and degraded/canceled -> failed;
    seven-key stats {total,pending,transferring,verifying,verify_failed,
    success,failed} always sums to total.
  - _maybe_finalize task aggregation rule: all success -> success; any mix that
    includes success -> partial; no success, only hard failures -> failed;
    all degraded (no success, no hard failure) -> partial.

DB-free: repository seams are mocked at the transfer_tasks/transfer_service
module namespace.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services import transfer_service
from app.tasks import transfer_tasks


# =============================================================== _stats folds


def test_stats_folds_pulling_into_transferring():
    stats = transfer_service._stats({"pulling": 2, "success": 1, "pending": 1})
    assert stats == {
        "total": 4, "pending": 1, "transferring": 2, "verifying": 0,
        "verify_failed": 0, "success": 1, "failed": 0,
    }


def test_stats_folds_degraded_canceled_into_failed():
    stats = transfer_service._stats({"failed": 1, "degraded": 1, "canceled": 2})
    assert stats["failed"] == 4
    assert stats["total"] == 4


def test_stats_seven_keys_conserve_total():
    for raw in (
        {"pending": 1, "success": 2},
        {"pulling": 1, "transferring": 1, "verifying": 1,
         "verify_failed": 1, "failed": 1, "degraded": 1, "canceled": 1},
        {},
    ):
        stats = transfer_service._stats(raw)
        assert set(stats) == {"total", "pending", "transferring", "verifying",
                              "verify_failed", "success", "failed"}
        assert stats["total"] == sum(v for k, v in stats.items() if k != "total")


# ======================================================= _maybe_finalize


class _Db:
    def commit(self):
        pass


class _TaskRepo:
    """Optimistic-update seam; records the write for assertion."""

    def __init__(self):
        self.writes = []

    def optimistic_update(self, task_id, from_status, to_status, version):
        self.writes.append((task_id, from_status, to_status, version))
        return True


class _HostRepo:
    def __init__(self, stats: dict, active: int = 0):
        self._stats = stats
        self._active = active

    def stats(self, task_id):
        return dict(self._stats)

    def active_count(self, task_id):
        return self._active


def _finalize(task, host_stats: dict, active: int = 0) -> tuple[_TaskRepo, dict | None]:
    db = _Db()
    task_repo = _TaskRepo()
    transfer_tasks.TransferHostRepository = lambda db, *a, **k: _HostRepo(host_stats, active)
    transfer_tasks.TransferTaskRepository = lambda db, *a, **k: task_repo
    transfer_tasks.transfer_dispatch  # ensure module import is stable
    transfer_tasks._maybe_finalize(db, task)
    return task_repo, getattr(task, "status", None)


def test_finalize_all_success_is_success():
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"success": 3})
    assert status == "success"
    assert task_repo.writes == [(1, "processing", "success", 0)]


def test_finalize_mixed_with_success_is_partial():
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    _, status = _finalize(task, {"success": 2, "degraded": 1})
    assert status == "partial"
    _, status = _finalize(task, {"success": 1, "failed": 1})
    assert status == "partial"


def test_finalize_all_degraded_is_partial_not_success():
    """Ruling: all-degraded (no success, no hard failure) -> partial, matching
    the 'degraded is not a failure' semantics for task aggregation."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"degraded": 3})
    assert status == "partial"
    assert task_repo.writes and task_repo.writes[0][2] == "partial"


def test_finalize_all_hard_failed_is_failed():
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    _, status = _finalize(task, {"failed": 2})
    assert status == "failed"
    _, status = _finalize(task, {"verify_failed": 2})
    assert status == "failed"


def test_finalize_verify_failed_counts_as_unsuccess():
    """Ruling: verify_failed merges into the hard-failure count for aggregation
    (no success -> failed; any success -> partial); the key stays observable."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    _, status = _finalize(task, {"success": 1, "verify_failed": 1})
    assert status == "partial"


def test_finalize_skips_when_hosts_still_active():
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"success": 1, "pulling": 1}, active=1)
    assert status == "processing"
    assert task_repo.writes == []


def test_finalize_skips_non_processing_task():
    task = SimpleNamespace(id=1, status="canceled", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"success": 1})
    assert status == "canceled"
    assert task_repo.writes == []