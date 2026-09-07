"""Stage-5 schedule service unit tests (api-design §8 schedules, US-08 in full).

Add-only state lock pinning the schedule module contract on the candidate tip
(after scheduled-ops P1 approval chain, local master c7c7138+2):

  S1  validate: kind=script requires script_id; command kind requires command;
      cron needs valid expr; interval needs interval_sec >= 1
  S2  create persists ScheduleTask (target_host_ids boxed, created_by set)
  S3  update missing -> NotFoundError; stored cron revalidated -> BadRequestError; ok
  S4  delete / set_status missing -> NotFoundError; ok paths commit
  S5  list_schedules: name+enabled filters, envelope {list,total,page,size}
  S6  _due_tasks: interval due on first run / elapsed / not-elapsed; cron next_run <= now
  S7  trigger_due: dispatch per due schedule ([schedule] prefix, owner requester);
      one broken schedule never aborts the sweep (rollback + failed ScheduleRun error_msg)
  S8  run_now missing -> NotFoundError; ok delegates to _spawn_run with requester
  S9  _spawn_run non-sensitive: run+task+task_hosts, CAS created->running, commit,
      _kick_off_exec(task id), 6-key result
  S10 _spawn_run sensitive: ApprovalRequest(biz_type=exec, pending) + awaiting_approval,
      CAS created->awaiting_approval, NO dispatch, 6-key result
  S11 _spawn_run errors: unknown host / missing script / missing script version /
      empty command -> NotFoundError / BadRequestError
  S12 retry_run: run missing or foreign schedule -> NotFoundError; CAS conflict ->
      ConflictError; failed task opt-run + host reset + orphan close + dispatch;
      sensitive retry -> awaiting_approval (sensitive_flag=1); no prior task ->
      fresh _spawn_run "[retry]"
  S13 list_runs: envelope via ScheduleRunRepository.runs_of
"""

from __future__ import annotations

import datetime as _dt
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.schemas import ScheduleCreate, ScheduleOut, ScheduleRunOut, ScheduleUpdate
from app.services import schedule_service


class _Db:
    def __init__(self, scalar=None, scalars=()):
        self.scalar_val = scalar
        self.scalars_val = list(scalars)
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.deleted = []
        self.next_id = 100

    def scalar(self, *a, **kw):
        return self.scalar_val

    def scalars(self, *a, **kw):
        return _Rows(self.scalars_val)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for o in self.added:
            if getattr(o, "id", None) is None:
                o.id = self.next_id
                self.next_id += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def delete(self, obj):
        self.deleted.append(obj)


class _Rows:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


def _sched(id=1, trigger_type="interval", interval_sec=60, cron_expr=None, kind="command",
           name="s", command="echo hi", script_id=None, created_by=1, target_host_ids=(1,),
           enabled=1):
    return SimpleNamespace(id=id, name=name, kind=kind, script_id=script_id, command=command,
                           params=None, trigger_type=trigger_type, cron_expr=cron_expr,
                           timezone="Asia/Shanghai", interval_sec=interval_sec,
                           target_host_ids={"ids": list(target_host_ids)}, timeout_sec=300,
                           retry=0, concurrency_limit=10, enabled=enabled, created_by=created_by)


def _user(uid=7):
    return SimpleNamespace(id=uid)


def _host(hid=1):
    return SimpleNamespace(id=hid, hostname=f"h{hid}", ip=f"10.0.0.{hid}", connector="agent")


def _task(id=10, status="failed", version=1, command="rm -rf /tmp/x", kind="command",
          script_id=None, script_version=None, target_host_ids=(1,), name="t"):
    return SimpleNamespace(id=id, task_no=f"T-{id}", name=name, kind=kind, command=command,
                           script_id=script_id, script_version=script_version,
                           target_host_ids={"ids": list(target_host_ids)},
                           status=status, version=version, sensitive_flag=0)


def _exec_service(monkeypatch, sensitive=False, reason=""):
    calls = {"kick": [], "close": []}
    monkeypatch.setattr("app.services.exec_service.detect_sensitive",
                        lambda db, cmd, sc, hc: (sensitive, reason))
    monkeypatch.setattr("app.services.exec_service._kick_off_exec",
                        lambda db, tid: calls["kick"].append(tid))
    monkeypatch.setattr("app.services.exec_service._close_orphan_approval",
                        lambda db, t: calls["close"].append(t.id))
    monkeypatch.setattr("app.services.exec_service._approval_no",
                        lambda db: "AP-20260906-900" + str(db.commits))
    return calls


def _models(db, monkeypatch, exec_host=True, approval=True):
    monkeypatch.setattr(schedule_service, "ScheduleRun",
                        lambda **kw: SimpleNamespace(id=None, **kw))
    monkeypatch.setattr(schedule_service, "ExecTask",
                        lambda **kw: SimpleNamespace(id=None, version=0, **kw))
    if approval:
        monkeypatch.setattr(schedule_service, "ApprovalRequest",
                            lambda **kw: SimpleNamespace(id=None, **kw))
    if exec_host:
        monkeypatch.setattr(schedule_service, "ExecTaskHost",
                            lambda **kw: SimpleNamespace(id=None, **kw))
        monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                            lambda d: SimpleNamespace(add=lambda o: db.add(o)))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: db.add(o),
                                                  optimistic_update=lambda *a: True))
    if approval:
        monkeypatch.setattr(schedule_service, "ApprovalRepository",
                            lambda d: SimpleNamespace(add=lambda o: db.add(o)))


def _by_attr(db, attr):
    return [o for o in db.added if hasattr(o, attr)]


def _cas(task):
    def _u(task_id, from_status, to_status, version):
        if task.id == task_id and task.status == from_status and task.version == version:
            task.status = to_status
            task.version += 1
            return True
        return False
    return _u


def _opt(monkeypatch, task):
    def _u(task_id, from_status, to_status, version):
        if task.id == task_id and task.status == from_status and task.version == version:
            task.status = to_status
            task.version += 1
            return True
        return False
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None, optimistic_update=_u))


# ------------------------------------------------------------------ S1/S2 validation + create


def test_s1_validate_kind_cron_interval():
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(ScheduleCreate(
            name="t", kind="script", command=None, target_host_ids=[1]))
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(ScheduleCreate(
            name="t", kind="command", command=None, target_host_ids=[1]))
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(ScheduleCreate(
            name="t", kind="command", command="ls", trigger_type="cron",
            cron_expr="not a cron", target_host_ids=[1]))
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(ScheduleCreate(
            name="t", kind="command", command="ls", trigger_type="interval",
            interval_sec=0, target_host_ids=[1]))
    with pytest.raises(BadRequestError):
        schedule_service._validate_schedule(ScheduleCreate(
            name="t", kind="command", command="ls", trigger_type="nope", target_host_ids=[1]))
    schedule_service._validate_schedule(ScheduleCreate(
        name="t", kind="command", command="ls", trigger_type="interval", interval_sec=60,
        target_host_ids=[1]))


def test_s2_create_persists_boxed(monkeypatch):
    db = _Db()
    created = []
    created_stub = None

    class _STask:
        def __init__(self, **kw):
            nonlocal created_stub
            self.__dict__.update(kw)
            self.id = 9
            created_stub = self
            created.append(self)

    monkeypatch.setattr(schedule_service, "ScheduleTask", _STask)
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(add=lambda o: None))
    uid = schedule_service.create_schedule(db, _user(uid=5), ScheduleCreate(
        name="nightly", kind="command", command="backup.sh", trigger_type="interval",
        interval_sec=3600, target_host_ids=[2, 3]))
    assert uid == 9
    assert created[0].target_host_ids == {"ids": [2, 3]}
    assert created[0].created_by == 5
    assert created[0].interval_sec == 3600
    assert db.commits == 1


# ------------------------------------------------------------------ S3/S4 update/delete/status


def test_s3_update_missing_then_ok_and_cron(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.update_schedule(db, 99, ScheduleUpdate(name="x"))

    sched = _sched(id=5, trigger_type="cron", cron_expr="*/5 * * * *")
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    schedule_service.update_schedule(db, 5, ScheduleUpdate(name="renamed", interval_sec=120))
    assert sched.name == "renamed"
    assert sched.interval_sec == 120
    assert db.commits == 1
    sched.cron_expr = "broken cron !!"
    with pytest.raises(BadRequestError):
        schedule_service.update_schedule(db, 5, ScheduleUpdate(name="again"))


def test_s4_delete_and_status(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.delete_schedule(db, 99)
    with pytest.raises(NotFoundError):
        schedule_service.set_schedule_status(db, 99, 0)

    sched = _sched()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    schedule_service.delete_schedule(db, 1)
    assert db.deleted == [sched]
    assert db.commits == 1
    db.commits = 0
    schedule_service.set_schedule_status(db, 1, 0)
    assert sched.enabled == 0
    assert db.commits == 1


def test_s5_list_schedules_envelope(monkeypatch):
    row = SimpleNamespace(id=1, name="s", kind="command", script_id=None, command="ls",
                          params=None, trigger_type="interval", cron_expr=None,
                          timezone="Asia/Shanghai", interval_sec=60,
                          target_host_ids={"ids": [1]}, timeout_sec=300, retry=0,
                          concurrency_limit=10, enabled=1, created_by=1,
                          created_at=datetime.now(timezone.utc))
    db = _Db(scalar=3, scalars=[row])
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository", lambda d: SimpleNamespace())
    out = schedule_service.list_schedules(db, None, None, 1, 10)
    assert out == {"list": [ScheduleOut.model_validate(row).model_dump()],
                   "total": 3, "page": 1, "size": 10}
    assert out["list"][0]["interval_sec"] == 60
    schedule_service.list_schedules(db, "s", 1, 1, 10)


# ------------------------------------------------------------------ S6 _due_tasks


def test_s6_due_interval_and_cron():
    now = datetime.now(timezone.utc)
    fresh = _sched(id=1, trigger_type="interval", interval_sec=3600)
    aging = _sched(id=2, trigger_type="interval", interval_sec=60)
    first = _sched(id=3, trigger_type="interval", interval_sec=60)
    cron_past = _sched(id=4, trigger_type="cron", cron_expr="* * * * *")
    cron_future = _sched(id=5, trigger_type="cron", cron_expr="* * * * *")
    db = _BucketDb([now - timedelta(seconds=10), now - timedelta(seconds=120), None])

    class _FakeRepo:
        def __init__(self, d):
            pass

        def enabled_tasks(self):
            return [fresh, aging, first]

    _orig = schedule_service.ScheduleTaskRepository
    schedule_service.ScheduleTaskRepository = lambda d: _FakeRepo(d)
    try:
        due = schedule_service._due_tasks(db)
    finally:
        schedule_service.ScheduleTaskRepository = _orig
    assert [t.id for t in due] == [2, 3]

    cron_db = _BucketDb([now - timedelta(seconds=150), now])

    class _CronRepo:
        def __init__(self, d):
            pass

        def enabled_tasks(self):
            return [cron_past, cron_future]

    schedule_service.ScheduleTaskRepository = lambda d: _CronRepo(d)
    try:
        due = schedule_service._due_tasks(cron_db)
    finally:
        schedule_service.ScheduleTaskRepository = _orig
    assert [t.id for t in due] == [4]


class _BucketDb:
    """Pops scalar picks queue items (interval due uses last-run lookups)."""

    def __init__(self, vals):
        self._vals = list(vals)

    def scalar(self, *a, **kw):
        return self._vals.pop(0) if self._vals else None


# ------------------------------------------------------------------ S7 trigger_due


def test_s7_trigger_due_dispatch_and_failure_isolation(monkeypatch):
    db = _Db()
    good = _sched(id=5, created_by=3)
    calls = []
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [good]))
    monkeypatch.setattr(schedule_service, "_spawn_run",
                        lambda _d, s, requester, prefix: calls.append((s.id, requester, prefix)) or
                        {"run_id": 1, "task_id": 2, "status": "running"})
    assert schedule_service.trigger_due(db) == 1
    assert calls == [(5, 3, "[schedule]")]

    db2 = _Db()

    def boom(_d, s, requester, prefix):
        raise RuntimeError("dispatch exploded")

    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(enabled_tasks=lambda: [good]))
    monkeypatch.setattr(schedule_service, "_spawn_run", boom)
    assert schedule_service.trigger_due(db2) == 0
    assert db2.rollbacks == 1
    failed = [o for o in db2.added if getattr(o, "status", "") == "failed"]
    assert len(failed) == 1
    assert "dispatch exploded" in failed[0].error_msg


# ------------------------------------------------------------------ S8 run_now


def test_s8_run_now_missing_then_delegates(monkeypatch):
    db = _Db()
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.run_now(db, _user(uid=9), 99)

    sched = _sched(id=5)
    calls = []
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    monkeypatch.setattr(schedule_service, "_spawn_run",
                        lambda d, s, requester, prefix: calls.append((s.id, requester, prefix)) or
                        {"run_id": 1, "task_id": 2, "status": "running"})
    out = schedule_service.run_now(db, _user(uid=9), 5)
    assert out["status"] == "running"
    assert calls == [(5, 9, "[run-now]")]


# ------------------------------------------------------------------ S9/S10 _spawn_run


def test_s9_spawn_run_nonsensitive_dispatch(monkeypatch):
    db = _Db()
    sched = _sched(id=5, command="echo hi", target_host_ids=(1, 2))
    _models(db, monkeypatch)
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: {1: _host(1), 2: _host(2)}[i]))
    calls = _exec_service(monkeypatch, sensitive=False)
    out = schedule_service._spawn_run(db, sched, 7, "[run-now]")
    assert out == {"run_id": 100, "task_id": 101, "status": "running",
                   "approve_required": False, "approval_id": None, "sensitive_flag": False}
    assert calls["kick"] == [101]
    assert db.commits == 1
    task = _by_attr(db, "task_no")[0]
    assert task.target_host_ids == {"ids": [1, 2]}
    assert task.created_by == 7
    assert task.sensitive_flag == 0 and task.approve_required == 0
    run = _by_attr(db, "run_no")[0]
    assert run.task_id == task.id
    hosts = _by_attr(db, "hostname")
    assert len(hosts) == 2


def test_s10_spawn_run_sensitive_approval(monkeypatch):
    db = _Db()
    sched = _sched(id=5, command="rm -rf /tmp", target_host_ids=(1,))
    _models(db, monkeypatch)
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: {1: _host(1)}[i]))
    calls = _exec_service(monkeypatch, sensitive=True, reason="keyword: rm -rf")
    out = schedule_service._spawn_run(db, sched, 7, "[schedule]")
    assert out == {"run_id": 100, "task_id": 101, "status": "awaiting_approval",
                   "approve_required": True, "approval_id": 103, "sensitive_flag": True}
    assert calls["kick"] == []          # approval-gated: no direct dispatch
    assert db.commits == 1
    task = _by_attr(db, "task_no")[0]
    assert task.approval_id == 103
    approval = _by_attr(db, "request_no")[0]
    assert approval.biz_type == "exec"
    assert approval.status == "pending"
    assert approval.requester_id == 7
    assert approval.sensitive_hit == "keyword: rm -rf"
    run = _by_attr(db, "run_no")[0]
    assert run.task_id == task.id


# ------------------------------------------------------------------ S11 spawn errors


def test_s11_spawn_run_errors(monkeypatch):
    db = _Db()
    _models(db, monkeypatch)
    monkeypatch.setattr(schedule_service, "HostRepository",
                        lambda d: SimpleNamespace(get=lambda i: {2: _host(2)}.get(i)))
    with pytest.raises(NotFoundError):
        schedule_service._spawn_run(db, _sched(target_host_ids=(99,)), 1, "[run-now]")

    sched = _sched(kind="script", script_id=9, target_host_ids=(2,))
    monkeypatch.setattr(schedule_service, "ScriptRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service._spawn_run(db, sched, 1, "[run-now]")

    script = SimpleNamespace(id=9, current_version=3)
    monkeypatch.setattr(schedule_service, "ScriptRepository",
                        lambda d: SimpleNamespace(get=lambda i: script))
    monkeypatch.setattr(schedule_service, "ScriptVersionRepository",
                        lambda d: SimpleNamespace(by_script_version=lambda sid, v: None))
    with pytest.raises(NotFoundError):
        schedule_service._spawn_run(db, sched, 1, "[run-now]")

    with pytest.raises(BadRequestError):
        schedule_service._spawn_run(db, _sched(kind="script", script_id=None,
                                               target_host_ids=(2,)), 1, "[run-now]")

    with pytest.raises(BadRequestError):
        schedule_service._spawn_run(db, _sched(kind="command", command=None,
                                               target_host_ids=(2,)), 1, "[run-now]")


# ------------------------------------------------------------------ S12 retry_run


def test_s12_retry_run(monkeypatch):
    db = _Db()
    run = SimpleNamespace(id=1, schedule_task_id=5, task_id=10, status="failed",
                          finished_at=None)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        schedule_service.retry_run(db, _user(), 5, 1)        # schedule missing
    run.schedule_task_id = 6
    with pytest.raises(NotFoundError):
        schedule_service.retry_run(db, _user(), 5, 1)        # foreign schedule
    run.schedule_task_id = 5

    # non-sensitive: CAS opt-run + host reset + orphan close + dispatch (3-key result)
    sched = _sched(id=5)
    task = _task(id=10, status="failed", version=1, command="echo hi")
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=_cas(task)))
    th_repo = SimpleNamespace(by_task=lambda i: [SimpleNamespace(id=1, status="failed")],
                              update_status=lambda *a: None)
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository", lambda d: th_repo)
    calls = _exec_service(monkeypatch, sensitive=False)
    out = schedule_service.retry_run(db, _user(), 5, 1)
    assert out == {"run_id": 1, "task_id": 10, "status": "running"}
    assert task.status == "running"
    assert calls["kick"] == [10]
    assert calls["close"] == [10]

    # sensitive retry -> awaiting_approval (6-key, sensitive_flag set, run reset)
    db = _Db()
    run = SimpleNamespace(id=1, schedule_task_id=5, task_id=10, status="failed",
                          finished_at=None)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    task = _task(id=10, status="failed", version=1, command="rm -rf /tmp")
    monkeypatch.setattr(schedule_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=_cas(task)))
    monkeypatch.setattr(schedule_service, "ScheduleTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: sched))
    _models_exec_host_only(monkeypatch)
    monkeypatch.setattr(schedule_service, "ApprovalRequest",
                        lambda **kw: SimpleNamespace(id=50, **kw))
    monkeypatch.setattr(schedule_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(add=lambda o: None))
    calls = _exec_service(monkeypatch, sensitive=True, reason="keyword: rm")
    out = schedule_service.retry_run(db, _user(), 5, 1)
    assert out == {"run_id": 1, "task_id": 10, "status": "awaiting_approval",
                   "approve_required": True, "approval_id": 50, "sensitive_flag": True}
    assert task.sensitive_flag == 1
    assert run.status == "running" and run.finished_at is None
    assert calls["kick"] == []

    # no prior task -> fresh _spawn_run "[retry]"
    db = _Db()
    run = SimpleNamespace(id=1, schedule_task_id=5, task_id=None)
    spawn_calls = []
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(get=lambda i: run))
    monkeypatch.setattr(schedule_service, "_spawn_run",
                        lambda d, s, requester, prefix: spawn_calls.append(
                            (s.id, requester, prefix)) or
                        {"run_id": 21, "task_id": 22, "status": "running"})
    out = schedule_service.retry_run(db, _user(), 5, 1)
    assert out == {"run_id": 21, "task_id": 22, "status": "running"}
    assert spawn_calls == [(5, 7, "[retry]")]


def _models_exec_host_only(monkeypatch):
    monkeypatch.setattr(schedule_service, "ExecTaskHostRepository",
                        lambda d: SimpleNamespace(add=lambda o: None,
                                                  by_task=lambda i: [],
                                                  update_status=lambda *a: None))


# ------------------------------------------------------------------ S13 list_runs


def test_s13_list_runs_envelope(monkeypatch):
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(id=1, schedule_task_id=5, run_no="R-5-20260906120000",
                          status="success", task_id=9, started_at=now,
                          finished_at=now, error_msg=None)
    monkeypatch.setattr(schedule_service, "ScheduleRunRepository",
                        lambda d: SimpleNamespace(
                            runs_of=lambda sid, p, s: ([run], 1)))
    out = schedule_service.list_runs(_Db(scalar=1, scalars=[run]), 5, 1, 10)
    assert out == {"list": [ScheduleRunOut.model_validate(run).model_dump()],
                   "total": 1, "page": 1, "size": 10}
    assert out["list"][0]["run_no"] == "R-5-20260906120000"