"""Stage-5 dashboard service unit tests (US-08 dashboard module, task-allocation stage5).

Add-only state lock pinning the dashboard module contract on the authoritative root
(green @ c7c7138, external run):

  D1 stats(admin): host totals / online / running / today counts / pending approvals
  D2 stats(non-admin, no visible groups): default-deny -> host_total 0, tasks scoped to self
  D3 task_trend: per-day buckets total/success/failed, dates newest-first
  D4 recent_tasks: latest 10 envelope [{id,task_no,name,status,kind,created_at}]
  D5 recent_approvals: latest 10 (requester-scoped for non-admin) shape
"""

from __future__ import annotations

import datetime as _dt
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from app.services import dashboard_service


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Db:
    def __init__(self, queue):
        self._queue = list(queue)

    def scalars(self, *a, **kw):
        return _Scalars(self._queue.pop(0) if self._queue else [])

    def scalar(self, *a, **kw):
        return self._queue.pop(0) if self._queue else 0


def _esp(online=True, group=1, hid=1):
    return SimpleNamespace(id=hid, status="online" if online else "offline", group_id=group)


def _ess(id, name, status, kind="command", created_at=None, created_by=1, task_no="T-1"):
    return SimpleNamespace(id=id, task_no=task_no, name=name, status=status, kind=kind,
                           created_at=created_at or datetime.now(timezone.utc),
                           created_by=created_by)


def _apv(id, request_no, title, status, requester_id=1, created_at=None):
    return SimpleNamespace(id=id, request_no=request_no, title=title, status=status,
                           requester_id=requester_id,
                           created_at=created_at or datetime.now(timezone.utc))


class _Admin:
    is_admin = True
    visible_group_ids = None


class _Deny:
    is_admin = False
    visible_group_ids = []
    id = 1


def test_d1_stats_admin_counts():
    now = datetime.now(timezone.utc)
    hosts = [_esp(True, hid=1), _esp(False, hid=2)]
    tasks = [
        _ess(1, "running", "running", created_by=1),
        _ess(2, "today ok", "success", created_by=1),
        _ess(3, "today running", "running", created_by=1),
        _ess(4, "old failed", "failed", created_at=now - timedelta(days=2), created_by=1),
    ]
    db = _Db([hosts, tasks, 2])
    out = dashboard_service.stats(db, _Admin())
    assert out == {
        "host_total": 2, "host_online": 1, "tasks_running": 2,
        "today_tasks": 3, "today_success": 1, "pending_approvals": 2,
    }


def test_d2_stats_non_admin_default_deny():
    hosts, tasks = [], [
        _ess(1, "mine running", "running", created_by=1),   # only self rows reach stats
    ]
    db = _Db([hosts, tasks, 0])
    out = dashboard_service.stats(db, _Deny())
    assert out["host_total"] == 0
    assert out["host_online"] == 0
    assert out["tasks_running"] == 1      # scoped to created_by == self
    assert out["today_tasks"] == 1
    assert out["today_success"] == 0
    assert out["pending_approvals"] == 0


def test_d3_task_trend_buckets():
    now = datetime.now(timezone.utc)
    day1 = _ess(1, "a", "success")
    day1_fail = _ess(2, "b", "failed")
    day0 = _ess(3, "c", "success")
    db = _Db([[day1, day1_fail], [day0]])
    out = dashboard_service.task_trend(db, _Admin(), days=2)
    assert len(out) == 2
    assert out[0]["date"] == (now - timedelta(days=1)).date().isoformat()
    assert out[0]["total"] == 2 and out[0]["success"] == 1 and out[0]["failed"] == 1
    assert out[1]["date"] == now.date().isoformat()
    assert out[1]["total"] == 1 and out[1]["success"] == 1 and out[1]["failed"] == 0


def test_d4_recent_tasks_shape():
    t1 = _ess(1, "one", "success", task_no="T-11")
    t2 = _ess(2, "two", "running", task_no="T-12")
    db = _Db([[t1, t2]])
    out = dashboard_service.recent_tasks(db, _Admin())
    assert out == [
        {"id": 1, "task_no": "T-11", "name": "one", "status": "success", "kind": "command",
         "created_at": t1.created_at.isoformat()},
        {"id": 2, "task_no": "T-12", "name": "two", "status": "running", "kind": "command",
         "created_at": t2.created_at.isoformat()},
    ]
    dashboard_service.recent_tasks(db, _Deny())


def test_d5_recent_approvals_shape():
    a1 = _apv(1, "A-1", "need ok", "pending")
    a2 = _apv(2, "A-2", "done", "approved")
    db = _Db([[a1, a2]])
    out = dashboard_service.recent_approvals(db, _Admin())
    assert out == [
        {"id": 1, "request_no": "A-1", "title": "need ok", "status": "pending",
         "created_at": a1.created_at.isoformat()},
        {"id": 2, "request_no": "A-2", "title": "done", "status": "approved",
         "created_at": a2.created_at.isoformat()},
    ]
    dashboard_service.recent_approvals(db, _Deny())