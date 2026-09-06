"""Schedule service unit tests (US-14 cron/interval scheduling, US-08 async runs).

Pins contract:
  S1  trigger_due runs interval tasks when no prior run / interval elapsed,
      and cron tasks when next_run <= now (via _due_tasks)
  S2  trigger_due creates ScheduleRun + ExecTask + ExecTaskHost and kicks off
      execution; returns count
  S3  create validates: script kind needs script_id, command kind needs command,
      cron needs valid expr, interval needs interval_sec >= 1
  S4  create_schedule persists ScheduleTask, wraps target_host_ids, returns id
  S5  update_schedule missing -> NotFoundError; invalid cron -> BadRequestError
  S6  delete/status missing -> NotFoundError
  S7  run_now creates run+task and returns {run_id, task_id, status, ...}
  S8  run_now on missing schedule -> NotFoundError
  S9  retry_run: run/schedule mismatch -> NotFoundError; failed task optimistic
      update to running (after re-sensitivity check); no prior task -> fresh run
  S10 repositories paginate list_schedules / list_runs
  S11 sensitive/oversized schedule (incl. run-now) -> biz_type=exec approval,
      NO direct dispatch (US-08 item 7 / GPT_12.8)
  S12 trigger_due isolates one failing schedule into a failed ScheduleRun and
      keeps sweeping
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import app.services.exec_service as exec_service

from app.core.exceptions import BadRequestError, NotFoundError
from app.schemas import ScheduleCreate, ScheduleUpdate
from app.services import schedule_service


class _Db:
    def __init__(self, scalar=None, scalars=()):
        self.scalar_val = scalar
        self.scalars_val = list(scalars)
        self.added = []
        self.commits = 0
        self.deleted = []

    def scalar(self, *a, **kw):
        return self.scalar_val

    def scalars(self, *a, **kw):
        return _Rows(self.scalars_val)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def delete(self, obj):
        self.deleted.append(obj)


class _Rows:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


def _schedule(id=1, trigger_type="interval", interval_sec=60, cron_expr=None,
              kind="command", command="echo hi", enabled=1, target_host_ids={"ids": [1]}):
    return SimpleNamespace(id=id, name="s", kind=kind, script_id=None, command=command,
                           params=None, trigger_type=trigger_type, cron_expr=cron_expr,
                           timezone="Asia/Shanghai", interval_sec=interval_sec,
                           target_host_ids=target_host_ids, timeout_sec=300, retry=0,
                           concurrency_limit=10, enabled=enabled, created_by=1)


def _user(uid=1):
    return SimpleNamespace(id=uid, is_admin=1)


def _host(hid=1):
    return SimpleNamespace(id=hid, hostname=f"h{hid}", ip="10.0.0.1", connector="agent")


def _run(id=1, schedule_id=1, task_id=10, status="running"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(id=id, schedule_task_id=schedule_id, run_no="R-1-20200101000000",
                           status=status, task_id=task_id, started_at=now,
                           finished_at=None, error_msg=None)


def _spawn_stubs(monkeypatch, sched_id="tasks", task_id=2, run_id=1):
    """Wire the repos that _spawn_run now touches, plus exec_service dispatch."""
    monkeypatch.setattr(schedule_service, "ScheduleRun",
                        lambda **kw: SimpleNamespace(id=run_id, **kw))
    monkeypatch.setattr(schedule_service, "ExecTask",
                        lambda **kw: SimpleNamespace(id=task_id, version=0, **kw))
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: _host(i)))
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, by_task=lambda t: [],
                                                  update_status=lambda *a: None))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, get=lambda i: None,
                                                  optimistic_update=lambda *a: True))


def _patch_exec(monkeypatch, sensitive, reason=""):
    kicked = []
    monkeypatch.setattr(exec_service, "detect_sensitive",
                        lambda db, cmd, content, n: (sensitive, reason))
    monkeypatch.setattr(exec_service, "_kick_off_exec",
                        lambda db, tid: kicked.append(tid))
    monkeypatch.setattr(exec_service, "_approval_no", lambda db: "AP-000")
    monkeypatch.setattr(exec_service, "_close_orphan_approval", lambda db, task: None)
    return kicked


# --- S1/S2 trigger ---------------------------------------------------------


def test_due_interval_no_prior_run(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5, trigger_type="interval", interval_sec=60)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [sched]))
    assert schedule_service._due_tasks(db) == [sched]


def test_due_interval_elapsed(monkeypatch):
    import datetime as _dt

    last = _dt.datetime.now(timezone.utc) - _dt.timedelta(seconds=120)
    sched = _schedule(id=5, trigger_type="interval", interval_sec=60)
    db = _Db(scalar=last)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [sched]))
    assert schedule_service._due_tasks(db) == [sched]


def test_due_not_elapsed(monkeypatch):
    import datetime as _dt

    last = _dt.datetime.now(timezone.utc) - _dt.timedelta(seconds=10)
    sched = _schedule(id=5, trigger_type="interval", interval_sec=3600)
    db = _Db(scalar=last)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [sched]))
    assert schedule_service._due_tasks(db) == []


def test_due_cron_next_past(monkeypatch):
    import datetime as _dt

    last = _dt.datetime.now(timezone.utc) - _dt.timedelta(minutes=5)
    sched = _schedule(id=5, trigger_type="cron", cron_expr="* * * * *")
    db = _Db(scalar=last)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [sched]))
    assert schedule_service._due_tasks(db) == [sched]


def test_trigger_due_dispatch(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5)
    monkeypatch.setattr(schedule_service, "_due_tasks", lambda d: [sched])
    _spawn_stubs(monkeypatch)
    kicked = _patch_exec(monkeypatch, sensitive=False)
    count = schedule_service.trigger_due(db)
    assert count == 1
    assert db.commits == 1
    assert kicked == [2]


def test_trigger_due_creates_host_rows(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5, target_host_ids={"ids": [3, 7]})
    monkeypatch.setattr(schedule_service, "_due_tasks", lambda d: [sched])
    hosts = []
    monkeypatch.setattr(schedule_service, "ScheduleRun",
                        lambda **kw: SimpleNamespace(id=1, **kw))
    monkeypatch.setattr(schedule_service, "ExecTask",
                        lambda **kw: SimpleNamespace(id=2, version=0, **kw))
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: _host(i)))
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                        lambda d: SimpleNamespace(add=hosts.append))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, get=lambda i: None,
                                                  optimistic_update=lambda *a: True))
    _patch_exec(monkeypatch, sensitive=False)
    assert schedule_service.trigger_due(db) == 1
    assert len(hosts) == 2
    assert {h.host_id for h in hosts} == {3, 7}


# --- S3/S4 create ----------------------------------------------------------


def test_create_validation_script_requires_id():
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(
            ScheduleCreate(name="s", kind="script", script_id=None, command=None,
                           trigger_type="interval", interval_sec=60, target_host_ids=[1]))

def test_create_validation_command_requires_command():
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(
            ScheduleCreate(name="s", kind="command", command=None, trigger_type="interval",
                           interval_sec=60, target_host_ids=[1]))

def test_create_validation_cron_invalid():
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(
            ScheduleCreate(name="s", kind="command", command="ls", trigger_type="cron",
                           cron_expr="bad expr", target_host_ids=[1]))

def test_create_validation_interval_must_be_positive():
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(
            ScheduleCreate(name="s", kind="command", command="ls", trigger_type="interval",
                           interval_sec=0, target_host_ids=[1]))

def test_create_schedule(monkeypatch):
    db = _Db()
    created = []

    class _STask:
        def __init__(self, **kw):
            self.__dict__.update(kw)
            self.id = 9
            created.append(self)

    monkeypatch.setattr(schedule_service, "ScheduleTask", _STask)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None))
    uid = schedule_service.create_schedule(db, _user(), ScheduleCreate(
        name="nightly", kind="command", command="backup.sh", trigger_type="interval",
        interval_sec=3600, target_host_ids=[1, 2]))
    assert uid == 9
    assert created[0].target_host_ids == {"ids": [1, 2]}
    assert created[0].created_by == 1
    assert db.commits == 1


# --- S5/S6 update/delete/status -------------------------------------------


def test_update_schedule_missing(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.update_schedule(db, 1, ScheduleUpdate(name="x"))


def test_update_schedule_invalid_cron(monkeypatch):
    db = _Db()
    sched = _schedule(trigger_type="cron", cron_expr="bad")
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    with pytest.raises(BadRequestError):
        schedule_service.update_schedule(db, 1, ScheduleUpdate(cron_expr="still bad"))


def test_update_schedule_ok(monkeypatch):
    db = _Db()
    sched = _schedule()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    schedule_service.update_schedule(db, 1, ScheduleUpdate(name="renamed", interval_sec=120))
    assert sched.name == "renamed"
    assert sched.interval_sec == 120
    assert db.commits == 1


def test_delete_schedule(monkeypatch):
    db = _Db()
    sched = _schedule()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    schedule_service.delete_schedule(db, 1)
    assert db.deleted == [sched]
    assert db.commits == 1


def test_delete_schedule_missing(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.delete_schedule(db, 99)


def test_set_schedule_status(monkeypatch):
    db = _Db()
    sched = _schedule(enabled=1)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    schedule_service.set_schedule_status(db, 1, 0)
    assert sched.enabled == 0
    assert db.commits == 1


# --- S7/S8 run_now ---------------------------------------------------------


def test_run_now(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    _spawn_stubs(monkeypatch, task_id=12, run_id=11)
    kicked = _patch_exec(monkeypatch, sensitive=False)
    out = schedule_service.run_now(db, _user(), 5)
    assert out["run_id"] == 11
    assert out["task_id"] == 12
    assert out["status"] == "running"
    assert out["approve_required"] is False
    assert out["sensitive_flag"] is False
    assert kicked == [12]
    assert db.commits == 1


def test_run_now_missing(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.run_now(db, _user(), 99)


# --- S9 retry_run ----------------------------------------------------------


def test_retry_run_mismatch(monkeypatch):
    db = _Db()
    run = _run(id=1, schedule_id=5)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    with pytest.raises(NotFoundError):
        schedule_service.retry_run(db, _user(), 99, 1)


def test_retry_run_optimistic_rerun(monkeypatch):
    db = _Db()
    run = _run(id=1, schedule_id=5, task_id=10, status="failed")
    sched = _schedule(id=5)
    task = SimpleNamespace(id=10, status="failed", version=1, kind="command",
                           script_id=None, command="echo hi",
                           target_host_ids={"ids": [10]}, approval_id=None,
                           script_version=None, started_at=None, finished_at=None)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=lambda *a: True))
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                        lambda d: SimpleNamespace(by_task=lambda t: [SimpleNamespace(id=1, status="failed")],
                                                  update_status=lambda *a: None))
    kicked = _patch_exec(monkeypatch, sensitive=False)
    out = schedule_service.retry_run(db, _user(), 5, 1)
    assert out == {"run_id": 1, "task_id": 10, "status": "running"}
    assert kicked == [10]
    assert db.commits == 1


def test_retry_run_no_prior_creates_new(monkeypatch):
    db = _Db(scalar=None)
    run = _run(id=1, schedule_id=5, task_id=None)
    sched = _schedule(id=5)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    _spawn_stubs(monkeypatch, task_id=22, run_id=21)
    kicked = _patch_exec(monkeypatch, sensitive=False)
    out = schedule_service.retry_run(db, _user(), 5, 1)
    assert out["run_id"] == 21
    assert out["task_id"] == 22
    assert out["status"] == "running"
    assert kicked == [22]


# --- S11 sensitivity -> approval chain (US-08 item 7 / GPT_12.8) -----------


def test_run_now_sensitive_routes_to_approval(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5, command="rm -rf /data")
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    _spawn_stubs(monkeypatch, task_id=12, run_id=11)
    _patch_exec(monkeypatch, sensitive=True, reason="sensitive word: rm -rf")
    approvals = []
    monkeypatch.setattr(schedule_service, "ApprovalRequest",
                        lambda **kw: SimpleNamespace(id=31, **kw))
    monkeypatch.setattr(schedule_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(add=approvals.append))
    out = schedule_service.run_now(db, _user(), 5)
    assert out == {"run_id": 11, "task_id": 12, "status": "awaiting_approval",
                   "approve_required": True, "approval_id": 31, "sensitive_flag": True}
    assert len(approvals) == 1
    assert approvals[0].biz_type == "exec"
    assert approvals[0].biz_id == 12
    assert approvals[0].requester_id == 1


def test_sensitive_run_never_dispatching(monkeypatch):
    db = _Db(scalar=None)
    sched = _schedule(id=5, target_host_ids={"ids": list(range(1, 51))})
    monkeypatch.setattr(schedule_service, "_due_tasks", lambda d: [sched])
    _spawn_stubs(monkeypatch)
    kicked = _patch_exec(monkeypatch, sensitive=True, reason="batch size >= threshold")
    approvals = []
    monkeypatch.setattr(schedule_service, "ApprovalRequest",
                        lambda **kw: SimpleNamespace(id=41, **kw))
    monkeypatch.setattr(schedule_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(add=approvals.append))
    assert schedule_service.trigger_due(db) == 1
    assert kicked == []
    assert len(approvals) == 1


# --- S12 trigger_due isolates a failing schedule ---------------------------


def test_trigger_due_records_failure_and_keeps_sweeping(monkeypatch):
    db = _Db(scalar=None)
    good = _schedule(id=5)
    bad_host_missing = _schedule(id=6, target_host_ids={"ids": [1, 42]})
    monkeypatch.setattr(schedule_service, "_due_tasks", lambda d: [bad_host_missing, good])
    monkeypatch.setattr(schedule_service, "ScheduleRun",
                        lambda **kw: SimpleNamespace(id=1, **kw))
    monkeypatch.setattr(schedule_service, "ExecTask",
                        lambda **kw: SimpleNamespace(id=2, version=0, **kw))
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: _host(i) if i != 42 else None))
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, by_task=lambda t: [],
                                                  update_status=lambda *a: None))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, get=lambda i: None,
                                                  optimistic_update=lambda *a: True))
    _patch_exec(monkeypatch, sensitive=False)
    assert schedule_service.trigger_due(db) == 1
    failed = [r for r in db.added if getattr(r, "status", None) == "failed"]
    assert len(failed) == 1
    assert failed[0].schedule_task_id == 6
    assert "host 42 not found" in (failed[0].error_msg or "")


# --- S10 list --------------------------------------------------------------


def _schedule_row(id=1):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(id=id, name="s", kind="command", script_id=None, command="ls",
                           params=None, trigger_type="interval", cron_expr=None,
                           timezone="Asia/Shanghai", interval_sec=60,
                           target_host_ids={"ids": [1]}, timeout_sec=300, retry=0,
                           concurrency_limit=10, enabled=1, created_by=1, created_at=now)


def test_list_schedules(monkeypatch):
    db = _Db(scalar=2, scalars=[_schedule_row(1), _schedule_row(2)])
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace())
    out = schedule_service.list_schedules(db, None, None, 1, 10)
    assert out["total"] == 2
    assert len(out["list"]) == 2
    assert out["list"][0]["trigger_type"] == "interval"


def test_list_runs(monkeypatch):
    db = _Db(scalar=1, scalars=[_run()])
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(runs_of=lambda sid, p, s: (_Rows([_run()]).all(), 1)))
    out = schedule_service.list_runs(db, 5, 1, 10)
    assert out["total"] == 1
    assert out["list"][0]["run_no"] == "R-1-20200101000000"