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

from app.core.exceptions import ForbiddenError
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

    def __init__(self, succeed: bool = True):
        self.writes = []
        self._succeed = succeed

    def optimistic_update(self, task_id, from_status, to_status, version):
        self.writes.append((task_id, from_status, to_status, version))
        return self._succeed


class _HostRepo:
    def __init__(self, stats: dict, active: int = 0):
        self._stats = stats
        self._active = active

    def stats(self, task_id):
        return dict(self._stats)

    def active_count(self, task_id):
        return self._active


def _finalize(task, host_stats: dict, active: int = 0,
              repo_ok: bool = True) -> tuple[_TaskRepo, dict | None]:
    db = _Db()
    task_repo = _TaskRepo(repo_ok)
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


# ============================================= v1.3 boundary pins (degraded/canceled
# merge, empty stats no-op, optimistic-update conflict)


def test_finalize_noop_on_empty_stats():
    """No host rows yet -> finalize is a no-op (no status change, no write)."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {})
    assert status == "processing"
    assert task_repo.writes == []


def test_finalize_canceled_only_is_failed():
    """canceled merges into the hard-failure count for task aggregation."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"canceled": 2})
    assert status == "failed"
    assert task_repo.writes[0][2] == "failed"


def test_finalize_degraded_plus_canceled_is_failed():
    """A hard terminal (canceled) next to degraded still fails the task."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"degraded": 1, "canceled": 2})
    assert status == "failed"
    assert task_repo.writes[0][2] == "failed"


def test_finalize_optimistic_update_conflict_is_noop():
    """Concurrent finalize: version-conflict update writes nothing; the task
    stays processing with version/finished_at untouched."""
    task = SimpleNamespace(id=1, status="processing", version=0, finished_at=None)
    task_repo, status = _finalize(task, {"success": 3}, repo_ok=False)
    assert status == "processing"
    assert task.version == 0
    assert task.finished_at is None
    assert task_repo.writes  # attempted write recorded, but rejected


# ============================================= transfer:task:log 'mine' endpoint
# (P2-1 closeout: viewer log entry, seq1696-1698). Freezes: task:log gate (NOT
# task:list), non-admin created_by filter (data isolation), _task_out shape.


class _User:
    def __init__(self, is_admin: bool = False, uid: int = 1, perms=()):
        self.is_admin = is_admin
        self.id = uid
        self.permissions = set(perms)

    def require_perm(self, code: str) -> None:
        if not self.is_admin and code not in self.permissions:
            raise ForbiddenError(f"permission denied: {code}")


class _SearchRepo:
    """TransferTaskRepository seam recording the search() argument for assertion."""

    def __init__(self, rows):
        self._rows = rows
        self.filters = None

    def search(self, filters, page, size):
        self.filters = dict(filters)
        return list(self._rows), len(self._rows)


class _MineHostRepo:
    """TransferHostRepository seam for mine: per-task TransferHost row list."""

    def __init__(self, hosts=None):
        self._hosts = hosts or {}

    def by_task(self, task_id):
        return list(self._hosts.get(task_id, []))


def _mine(user, filters=None, rows=None, hosts=None):
    filters = filters or {}
    repo = _SearchRepo(rows or [])
    transfer_service.TransferTaskRepository = lambda db, *a, **k: repo
    transfer_service.TransferHostRepository = lambda db, *a, **k: _MineHostRepo(hosts)
    result = transfer_service.list_my_tasks(
        None, user, filters.get("mode"), filters.get("status"),
        None, None, 1, 10,
    )
    return repo, result


def test_mine_requires_task_log_not_task_list():
    """viewer (task:log, no task:list) reaches mine; a user without task:log is 403."""
    viewer = _User(uid=26, perms={"transfer:task:log"})
    repo, _ = _mine(viewer)
    assert repo.filters is not None

    no_log = _User(uid=1, perms={"transfer:task:list"})
    with pytest.raises(ForbiddenError):
        _mine(no_log)


def test_mine_filters_created_by_for_non_admin():
    """mine for a viewer/operator passes created_by=user.id to the shared filter
    bottom layer (same search() as list_tasks), so data isolation is intact."""
    viewer = _User(uid=26, perms={"transfer:task:log"})
    repo, result = _mine(viewer)
    assert repo.filters["created_by"] == 26
    assert result == {"list": [], "total": 0, "page": 1, "size": 10}


def test_mine_admin_has_no_own_filter():
    """admin may enumerate all tasks (no created_by constraint)."""
    admin = _User(is_admin=True, uid=24)
    repo, result = _mine(admin)
    assert "created_by" not in repo.filters
    assert result["total"] == 0


def test_mine_reuses_task_out_shape_zero_drift():
    """mine rows carry the same _task_out fields as list_tasks: id (task_id) +
    host_ids record (asset id space), so the frontend log dropdown can reach
    logs/ws-token; hosts (TransferHost row id space) is the additive field."""
    rows = [
        SimpleNamespace(
            id=7, task_no="TF-20260916-007", mode="push", package_id=3,
            source_host_id=1, source_host_path="/a", target_path="/b",
            host_ids={"ids": [11, 12]}, overwrite=True, verify=True,
            limit_mbps=None, status="processing", created_by=26,
            created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            started_at=None, finished_at=None,
        )
    ]
    # TransferHost rows: row id 26/27 (NOT asset ids 11/12) -> two id spaces distinct.
    host_rows = [
        SimpleNamespace(id=26, hostname="agent-001"),
        SimpleNamespace(id=27, hostname="agent-002"),
    ]
    viewer = _User(uid=26, perms={"transfer:task:log"})
    repo, result = _mine(viewer, rows=rows, hosts={7: host_rows})
    row = result["list"][0]
    assert row["id"] == 7
    assert row["host_ids"] == {"ids": [11, 12]}
    assert set(row) - {"hosts"} == set(transfer_service._task_out(rows[0]))
    assert set(row) == set(transfer_service._task_out(rows[0])) | {"hosts"}


def test_mine_hosts_shape_row_id_plus_hostname():
    """方案B (seq1724): hosts = [{id, hostname}] where id is the TransferHost
    ROW id and hostname the display name - directly usable for logs/ws-token."""
    rows = [
        SimpleNamespace(
            id=7, task_no="TF-20260916-007", mode="push", package_id=3,
            source_host_id=1, source_host_path="/a", target_path="/b",
            host_ids={"ids": [11, 12]}, overwrite=True, verify=True,
            limit_mbps=None, status="processing", created_by=26,
            created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            started_at=None, finished_at=None,
        )
    ]
    viewer = _User(uid=26, perms={"transfer:task:log"})
    _, result = _mine(
        viewer, rows=rows,
        hosts={7: [SimpleNamespace(id=26, hostname="agent-001"),
                   SimpleNamespace(id=27, hostname="agent-002")]},
    )
    assert result["list"][0]["hosts"] == [
        {"id": 26, "hostname": "agent-001"},
        {"id": 27, "hostname": "agent-002"},
    ]


def test_mine_two_id_spaces_do_not_mix():
    """Ruling seq1722/1724: host_ids.ids (asset Host id) NEVER equals hosts[].id
    (TransferHost row id); feeding asset id into logs would 404. The lock
    asserts the spaces are observably parent/child distinct."""
    rows = [
        SimpleNamespace(
            id=7, task_no="TF-20260916-007", mode="push", package_id=3,
            source_host_id=1, source_host_path="/a", target_path="/b",
            host_ids={"ids": [11, 12]}, overwrite=True, verify=True,
            limit_mbps=None, status="processing", created_by=26,
            created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            started_at=None, finished_at=None,
        )
    ]
    host_rows = [SimpleNamespace(id=26, hostname="agent-001")]
    viewer = _User(uid=26, perms={"transfer:task:log"})
    _, result = _mine(viewer, rows=rows, hosts={7: host_rows})
    row = result["list"][0]
    asset_ids = row["host_ids"]["ids"]
    transfer_ids = [h["id"] for h in row["hosts"]]
    assert 11 in asset_ids and 12 in asset_ids
    assert transfer_ids == [26]
    assert set(asset_ids).isdisjoint(transfer_ids), "asset/transfer id spaces must not overlap"


def test_mine_hosts_empty_when_no_transfer_host_rows():
    """A task row with no TransferHost rows yet (or pre-summary) yields hosts: []
    rather than a crash or a missing key - the UI degrades gracefully."""
    rows = [
        SimpleNamespace(
            id=8, task_no="TF-20260916-008", mode="push", package_id=4,
            source_host_id=None, source_host_path=None, target_path="/x",
            host_ids={"ids": [1]}, overwrite=True, verify=True,
            limit_mbps=None, status="processing", created_by=26,
            created_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            started_at=None, finished_at=None,
        )
    ]
    viewer = _User(uid=26, perms={"transfer:task:log"})
    _, result = _mine(viewer, rows=rows)
    assert result["list"][0]["hosts"] == []
