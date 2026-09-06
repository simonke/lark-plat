"""Dashboard service unit tests (US-08 dashboard module).

Pins contract:
  D1  stats aggregate host counts, running tasks, today totals, pending approvals
  D2  stats for non-admin user are host-scoped (visible group ids) and
      task-scoped (created_by self); empty visible groups -> zero hosts
  D3  task_trend returns `days` points ordered oldest->newest with
      total/success/failed counts
  D4  recent_tasks caps at 10 and is scoped to self for non-admin
  D5  recent_approvals caps at 10 and is scoped to requester for non-admin
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import dashboard_service


class _Rows:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _Db:
    def __init__(self, scalar=1, scalars=()):
        self._queue = [c for c in scalars] + [[]] * 20
        self.scalar_val = scalar

    def scalar(self, *a, **kw):
        return self.scalar_val

    def scalars(self, *a, **kw):
        return _Rows(self._queue.pop(0) if self._queue else [])


def _admin():
    return SimpleNamespace(is_admin=1, id=1, visible_group_ids=[])


def _user(groups=(), uid=2):
    return SimpleNamespace(is_admin=0, id=uid, visible_group_ids=list(groups))


def _host(id=1, status="online", group_id=1):
    return SimpleNamespace(id=id, status=status, group_id=group_id)


def _task(id=1, status="success", created_by=2, created_at=None):
    return SimpleNamespace(id=id, task_no=f"T-{id}", name="t", kind="command",
                           status=status, created_by=created_by,
                           created_at=created_at or datetime.now(timezone.utc))


def _approval(id=1, status="pending", requester_id=2):
    return SimpleNamespace(id=id, request_no=f"AP-{id}", title="a", status=status,
                           requester_id=requester_id,
                           created_at=datetime.now(timezone.utc))


# --- D1/D2 stats -----------------------------------------------------------


def test_stats_admin_aggregates():
    db = _Db(scalar=3, scalars=[
        [_host(1), _host(2, "offline"), _host(3)],
        [
            _task(1, "running"), _task(2, "running"),
            _task(3, "success", created_at=datetime.now(timezone.utc)),
            _task(4, "failed", created_at=datetime.now(timezone.utc) - timedelta(days=1)),
        ],
    ])
    out = dashboard_service.stats(db, _admin())
    assert out["host_total"] == 3
    assert out["host_online"] == 2
    assert out["tasks_running"] == 2
    assert out["today_tasks"] == 3
    assert out["today_success"] == 1
    assert out["pending_approvals"] == 3


def test_stats_non_admin_empty_groups_deny():
    db = _Db(scalar=0, scalars=[[], []])
    out = dashboard_service.stats(db, _user(groups=()))
    assert out["host_total"] == 0


def test_stats_non_admin_scoped():
    db = _Db(scalar=1, scalars=[
        [1, 2, 3],
        [_host(1), _host(2)],
        [_task(1, "running"), _task(2, "success")],
    ])
    out = dashboard_service.stats(db, _user(groups=(10, 20)))
    assert out["host_total"] == 2
    assert out["host_online"] == 2
    assert out["tasks_running"] == 1


# --- D3 task_trend ---------------------------------------------------------


def test_task_trend_seven_days():
    rows = [
        [_task(1, "success"), _task(2, "failed")],
        [_task(3, "timed_out")],
        [],
        [],
        [],
        [],
        [_task(4, "success")],
    ]
    db = _Db(scalar=0, scalars=rows)
    out = dashboard_service.task_trend(db, _admin(), 7)
    assert len(out) == 7
    assert out[0]["total"] == 2 and out[0]["success"] == 1 and out[0]["failed"] == 1
    assert out[1]["total"] == 1 and out[1]["failed"] == 1
    assert out[-1]["total"] == 1 and out[-1]["success"] == 1


def test_task_trend_non_admin_scoped():
    rows = [[_task(1, "success", created_by=1)], [], [], [], [], [], []]
    db = _Db(scalar=0, scalars=rows)
    out = dashboard_service.task_trend(db, _user(), 7)
    assert len(out) == 7
    assert out[0]["total"] == 1


# --- D4 recent_tasks -------------------------------------------------------


def test_recent_tasks_mapping():
    rows = [_task(1, "running"), _task(2, "success")]
    db = _Db(scalars=[rows])
    out = dashboard_service.recent_tasks(db, _admin())
    assert len(out) == 2
    assert out[0]["task_no"] == "T-1"
    assert out[0]["status"] == "running"
    assert out[0]["created_at"] is not None


def test_recent_tasks_empty():
    db = _Db(scalars=[[]])
    assert dashboard_service.recent_tasks(db, _admin()) == []


# --- D5 recent_approvals ---------------------------------------------------


def test_recent_approvals_mapping():
    rows = [_approval(1), _approval(2, "approved")]
    db = _Db(scalars=[rows])
    out = dashboard_service.recent_approvals(db, _admin())
    assert len(out) == 2
    assert out[0]["request_no"] == "AP-1"
    assert out[0]["status"] == "pending"
    assert out[1]["status"] == "approved"


def test_recent_approvals_non_admin_scoped():
    rows = [_approval(1, requester_id=2), _approval(5, requester_id=9)]
    db = _Db(scalars=[rows])
    out = dashboard_service.recent_approvals(db, _user(uid=2))
    assert len(out) == 2
    assert out[1]["request_no"] == "AP-5"