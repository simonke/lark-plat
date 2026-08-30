"""Stage-3 backend guards: exec gap closure (G1/G2/G4/G5/G7/G8/G10).

Pins the fixed behaviour from `gap-checklist.md` (baseline 8157eb0) so the
chain-3 re-run cannot silently regress:
  G1  script content actually resolved (not "script placeholder")
  G2  agent exec_log/exec_result are broadcast to user WS /ws/exec/{task_host_id}
  G4  stop dispatches an S->C stop frame to the host's agent
  G5  dispatch releases semaphores on every path (incl. execution errors)
  G7  awaiting_approval is exempt from the timeout sweep
  G8  retry re-runs sensitive detection and closes orphan approvals
  G10 list_tasks limits non-admin users to their own tasks
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import exec_service
from app.tasks import exec_tasks as et
from app.ws import agent_ws

_REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- G1


class _Svc:
    def __init__(self, sv, version=None):
        self.sv = sv
        self.version = version

    def by_script_version(self, script_id, version):
        if self.version is None or version == self.version:
            return self.sv
        return None


def _task(**kw):
    base = dict(task_no="T-1", kind="command", script_id=None, script_version=None,
                command="echo hi", params=None, timeout_sec=30, status="running")
    base.update(kw)
    return SimpleNamespace(**base)


def test_g1_resolve_content_reads_script_version_content(monkeypatch):
    sv = SimpleNamespace(content="echo {{NAME}}")
    monkeypatch.setattr(et, "ScriptVersionRepository", lambda db: _Svc(sv, version=3))
    monkeypatch.setattr(et, "ScriptRepository", lambda db: SimpleNamespace(get=lambda i: None))
    task = _task(kind="script", script_id=2, script_version=3, params={"NAME": "world"})
    assert et._resolve_content(None, task) == "echo world"


def test_g1_resolve_content_falls_back_to_current_version(monkeypatch):
    sv = SimpleNamespace(content="exit 0")
    script = SimpleNamespace(id=2, current_version=1)
    monkeypatch.setattr(
        et, "ScriptVersionRepository",
        lambda db: _Svc(sv, version=1),  # explicitly requested version has no match
    )
    monkeypatch.setattr(et, "ScriptRepository", lambda db: SimpleNamespace(get=lambda i: script))
    task = _task(kind="script", script_id=2, script_version=99)
    assert et._resolve_content(None, task) == "exit 0"


def test_g1_resolve_content_command_kind_uses_command(monkeypatch):
    monkeypatch.setattr(et, "ScriptVersionRepository", lambda db: _Svc(None))
    task = _task(kind="command", command="df -kh")
    assert et._resolve_content(None, task) == "df -kh"


def test_g1_no_script_placeholder_or_dynamic_import_left():
    src = (_REPO / "app" / "tasks" / "exec_tasks.py").read_text(encoding="utf-8")
    assert "script placeholder" not in src
    assert "__import__" not in src


# ---------------------------------------------------------------- G5 / N12/N13/P14


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.closed = False

    def commit(self):
        self.commits += 1

    def flush(self):
        pass

    def rollback(self):
        pass

    def close(self):
        self.closed = True

    def scalar(self, *a, **kw):
        return 0


class FakeHost:
    def __init__(self, host_id):
        self.id = host_id
        self.host_id = host_id
        self.status = "pending"
        self.started_at = None
        self.exit_code = None
        self.finished_at = None
        self.executor = "agent"


class FakeTaskRepo:
    def __init__(self, task):
        self.task = task

    def get(self, task_id):
        return self.task


class FakeThRepo:
    def __init__(self, hosts, the_map=None, stats=None):
        self.hosts = hosts
        self.the_map = the_map or {h.id: h for h in hosts}
        self.stats_result = stats or {}

    def by_task(self, task_id):
        return self.hosts

    def by_id(self, th_id):
        return self.the_map.get(th_id)

    def stats(self, task_id):
        return self.stats_result


def _patch_dispatch_env(monkeypatch, th_repo, execute, dispatch_frame=False):
    task = _task()
    db = FakeDb()
    monkeypatch.setattr(et, "_new_session", lambda: db)
    monkeypatch.setattr(et, "ExecTaskRepository", lambda s: FakeTaskRepo(task))
    monkeypatch.setattr(et, "ExecTaskHostRepository", lambda s: th_repo)
    monkeypatch.setattr(et, "_concurrency_limits", lambda s: (50, 5))
    monkeypatch.setattr(et, "_resolve_content", lambda s, t: "echo hi")
    monkeypatch.setattr(et, "_dispatch_exec_frame", lambda s, t, th, c: dispatch_frame)
    monkeypatch.setattr(et, "_execute_via_mock", execute)
    monkeypatch.setattr(et, "broadcast_sync", lambda *a, **kw: None)
    return task, db


def test_g5_dispatch_releases_semaphores_on_exec_error(monkeypatch):
    h1 = FakeHost(5)
    acquired, released = [], []

    def fail_execute(task, th, content, timeout_sec, params):
        raise RuntimeError("boom")

    th_repo = FakeThRepo([h1])
    _patch_dispatch_env(monkeypatch, th_repo, fail_execute, dispatch_frame=False)
    monkeypatch.setattr(et, "acquire_semaphore",
                        lambda key, lim: acquired.append(key) or True)
    monkeypatch.setattr(et, "release_semaphore", lambda key: released.append(key))

    with pytest.raises(RuntimeError):
        et.exec_dispatch(1)

    assert Counter(released) == Counter(acquired), (
        "every acquired semaphore must be released on the error path (G5/N13)"
    )
    assert Counter(acquired) == Counter(["exec:global", "exec:host:5"])


def test_g5_dispatch_happy_path_aggregates_success(monkeypatch):
    h1, h2 = FakeHost(5), FakeHost(6)

    def execute(task, th, content, timeout_sec, params):
        th.status = "success"
        th.exit_code = 0
        th.finished_at = None

    th_repo = FakeThRepo([h1, h2], stats={"success": 2})
    task, _ = _patch_dispatch_env(monkeypatch, th_repo, execute)
    monkeypatch.setattr(et, "acquire_semaphore", lambda key, lim: True)
    monkeypatch.setattr(et, "release_semaphore", lambda key: None)

    result = et.exec_dispatch(1)
    assert result["status"] == "success"
    assert task.status == "success"
    assert task.finished_at is not None


def test_dispatch_does_not_fail_while_hosts_still_running(monkeypatch):
    h1 = FakeHost(5)
    th_repo = FakeThRepo([h1], stats={"running": 1})
    task, _ = _patch_dispatch_env(monkeypatch, th_repo, lambda *a, **kw: None,
                                  dispatch_frame=True)
    monkeypatch.setattr(et, "acquire_semaphore", lambda key, lim: True)
    monkeypatch.setattr(et, "release_semaphore", lambda key: None)

    result = et.exec_dispatch(1)
    assert result["status"] == "running"
    assert h1.status == "running", "agent-dispatched hosts stay running"
    assert task.status == "running"


def test_semaphore_full_keeps_host_pending(monkeypatch):
    h1 = FakeHost(5)
    th_repo = FakeThRepo([h1])
    _patch_dispatch_env(monkeypatch, th_repo, lambda *a, **kw: None)
    monkeypatch.setattr(et, "acquire_semaphore", lambda key, lim: False)
    released = []
    monkeypatch.setattr(et, "release_semaphore", lambda key: released.append(key))

    result = et.exec_dispatch(1)
    assert result["ok"] is False and result["reason"] == "concurrency limit"
    assert h1.status == "pending", "saturated semaphore must not start hosts (N12)"
    assert released == []


def test_dispatch_agent_frame_shape(monkeypatch):
    captured = {}

    def fake_dispatch(agent_id, frame):
        captured["agent_id"] = agent_id
        captured["frame"] = frame
        return True

    monkeypatch.setattr(et, "dispatch_to_agent_sync", fake_dispatch)
    monkeypatch.setattr(et, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: SimpleNamespace(agent_id="a1")))
    task = SimpleNamespace(task_no="T-9", kind="script", params={"x": 1}, timeout_sec=60)
    th = SimpleNamespace(id=55, host_id=5, executor="agent")
    assert et._dispatch_exec_frame(None, task, th, "echo content") is True
    frame = captured["frame"]
    assert frame["type"] == "exec"
    assert frame["data"]["task_host_id"] == 55
    assert frame["data"]["command"] == "echo content"
    assert frame["data"]["task_no"] == "T-9"


def test_dispatch_agent_offline_falls_back(monkeypatch):
    calls = []
    monkeypatch.setattr(et, "dispatch_to_agent_sync", lambda a, f: calls.append(a) or True)
    monkeypatch.setattr(et, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: SimpleNamespace(agent_id=None)))
    th = SimpleNamespace(id=56, host_id=6, executor="agent", hostname="h")
    task = SimpleNamespace()
    assert et._dispatch_exec_frame(None, task, th, "x") is False
    assert calls == []


# ---------------------------------------------------------------- G7


def test_g7_scan_timeouts_excludes_awaiting_approval_src():
    src = (_REPO / "app" / "tasks" / "exec_tasks.py").read_text(encoding="utf-8")
    seg = src[src.index("def scan_timeouts"):]
    line = next(l for l in seg.splitlines() if "ExecTask.status" in l and "filter" in l)
    assert "running" in line
    assert "awaiting_approval" not in line


def test_g7_scan_timeouts_runs_without_error(monkeypatch):
    class FakeQuery:
        def filter(self, *a):
            return self

        def all(self):
            return []

    class FakeScanDb:
        def query(self, kls):
            return FakeQuery()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(et, "_new_session", lambda: FakeScanDb())
    monkeypatch.setattr(et, "ExecTaskRepository",
                        lambda db: SimpleNamespace(optimistic_update=lambda *a: True))
    monkeypatch.setattr(et, "ExecTaskHostRepository",
                        lambda db: SimpleNamespace(by_task=lambda tid: []))
    assert et.scan_timeouts() == 0


# ---------------------------------------------------------------- G2


class FakeSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def flush(self):
        pass

    def close(self):
        pass


@pytest.mark.asyncio
async def test_g2_persist_logs_broadcasts_each_item(monkeypatch):
    items = [
        {"task_host_id": 1, "seq": 1, "level": "info", "content": "a"},
        {"task_host_id": 1, "seq": 2, "level": "info", "content": "b"},
    ]
    appended, broadcasted = [], []
    monkeypatch.setattr(agent_ws, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(agent_ws, "ExecLogRepository",
                        lambda db: SimpleNamespace(append=lambda *a: appended.append(a)))

    async def fake_broadcast(th_id, msg):
        broadcasted.append((th_id, msg))

    monkeypatch.setattr(agent_ws, "broadcast", fake_broadcast)
    await agent_ws._persist_logs({"items": items})

    assert len(appended) == 2
    assert broadcasted[0][0] == 1
    assert broadcasted[0][1]["type"] == "log"
    assert broadcasted[0][1]["data"]["seq"] == 1
    assert broadcasted[1][1]["data"]["content"] == "b"


@pytest.mark.asyncio
async def test_g2_persist_result_broadcasts_and_finalizes(monkeypatch):
    th = SimpleNamespace(id=7, exec_task_id=3, host_id=3, hostname="h", ip="")
    task = SimpleNamespace(id=3, status="running", version=0, finished_at=None)
    updated, broadcasted = [], []

    class FakeThRepo:
        def by_id(self, th_id):
            return th

        def update_status(self, th_id, status, **kw):
            updated.append((th_id, status, kw))

        def stats(self, task_id):
            return {"success": 1}

    class FakeTaskRepo:
        def get(self, task_id):
            return task

        def optimistic_update(self, task_id, from_, to, version):
            assert from_ == "running" and to == "success"
            task.version = version + 1
            task.status = to
            return True

    monkeypatch.setattr(agent_ws, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(agent_ws, "ExecTaskHostRepository", lambda db: FakeThRepo())
    monkeypatch.setattr(agent_ws, "ExecTaskRepository", lambda db: FakeTaskRepo())

    async def fake_broadcast(th_id, msg):
        broadcasted.append((th_id, msg))

    monkeypatch.setattr(agent_ws, "broadcast", fake_broadcast)
    await agent_ws._persist_result({"task_host_id": 7, "status": "success", "exit_code": 0})

    assert updated[0][1] == "success"
    types = [m["type"] for _, m in broadcasted]
    assert "status" in types and "result" in types
    assert task.status == "success"
    assert task.finished_at is not None


@pytest.mark.asyncio
async def test_g2_stopped_result_maps_to_canceled(monkeypatch):
    th = SimpleNamespace(id=8, exec_task_id=4, host_id=4, hostname="h", ip="")
    updated = []

    class FakeThRepo:
        def by_id(self, th_id):
            return th

        def update_status(self, th_id, status, **kw):
            updated.append(status)

        def stats(self, task_id):
            return {}

    class FakeTaskRepo:
        def get(self, task_id):
            return None

        def optimistic_update(self, *a):
            return False

    monkeypatch.setattr(agent_ws, "SessionLocal", lambda: FakeSession())
    monkeypatch.setattr(agent_ws, "ExecTaskHostRepository", lambda db: FakeThRepo())
    monkeypatch.setattr(agent_ws, "ExecTaskRepository", lambda db: FakeTaskRepo())

    async def fake_broadcast(th_id, msg):
        pass

    monkeypatch.setattr(agent_ws, "broadcast", fake_broadcast)
    await agent_ws._persist_result({"task_host_id": 8, "status": "stopped"})
    assert updated == ["canceled"]


# ---------------------------------------------------------------- G4


def test_g4_stop_dispatches_agent_stop_frame(monkeypatch):
    user = SimpleNamespace(id=1, is_admin=1, require_perm=lambda p: None)
    task = SimpleNamespace(id=9, status="running", version=0, created_by=1, finished_at=None)
    th = SimpleNamespace(id=77, host_id=5, status="running")
    calls = []

    class FakeTaskRepo:
        def get(self, t_id):
            return task

        def optimistic_update(self, t_id, from_, to, version):
            task.version = version + 1
            return True

    class FakeThRepo:
        def by_task(self, t_id):
            return [th]

        def update_status(self, *a, **kw):
            pass

    monkeypatch.setattr(exec_service, "ExecTaskRepository", lambda db: FakeTaskRepo())
    monkeypatch.setattr(exec_service, "ExecTaskHostRepository", lambda db: FakeThRepo())
    monkeypatch.setattr(exec_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: SimpleNamespace(agent_id="a1")))

    def fake_dispatch(agent_id, frame):
        calls.append((agent_id, frame))
        return True

    monkeypatch.setattr(exec_service, "dispatch_to_agent_sync", fake_dispatch)
    result = exec_service.stop_task(FakeSession(), user, 9)

    assert result["status"] == "canceled"
    assert calls == [("a1", {"type": "stop", "data": {"task_host_id": 77}})]


# ---------------------------------------------------------------- G8


def test_g8_retry_rechecks_sensitivity_and_routes_to_approval(monkeypatch):
    user = SimpleNamespace(id=1, is_admin=1, require_perm=lambda p: None)
    task = SimpleNamespace(id=1, status="failed", version=0, name="t", task_no="N",
                           kind="command", command="rm -rf /x", script_id=None,
                           script_version=None, params=None, target_host_ids={"ids": [1]},
                           approval_id=None, sensitive_flag=0, created_by=1)
    approvals = []

    class FakeTaskRepo:
        def get(self, t_id):
            return task

        def optimistic_update(self, t_id, from_, to, version):
            task.version = version + 1
            task.status = to
            return True

    class FakeApprRepo:
        def add(self, obj):
            approvals.append(obj)

        def get(self, a_id):
            return None

        def optimistic_update(self, *a):
            return True

    monkeypatch.setattr(exec_service, "ExecTaskRepository", lambda db: FakeTaskRepo())
    monkeypatch.setattr(exec_service, "ApprovalRepository", lambda db: FakeApprRepo())
    monkeypatch.setattr(exec_service, "detect_sensitive",
                        lambda db, c, sc, hc: (True, "sensitive word: rm"))
    monkeypatch.setattr(exec_service, "_approval_no", lambda db: "AP-1")

    result = exec_service.retry_task(FakeSession(), user, 1)

    assert result["status"] == "awaiting_approval"
    assert task.status == "awaiting_approval"
    assert task.sensitive_flag == 1
    assert approvals and approvals[0].status == "pending"
    assert approvals[0].reason.startswith("重试触发敏感复检")


def test_g8_retry_closes_orphan_pending_approval(monkeypatch):
    user = SimpleNamespace(id=1, is_admin=1, require_perm=lambda p: None)
    task = SimpleNamespace(id=2, status="canceled", version=0, name="t", task_no="N",
                           kind="command", command="echo hi", script_id=None,
                           script_version=None, params=None, target_host_ids={"ids": [1]},
                           approval_id=9, sensitive_flag=0, created_by=1,
                           started_at=None, finished_at="old")
    approval = SimpleNamespace(id=9, status="pending", version=0)
    transitions = []

    class FakeTaskRepo:
        def get(self, t_id):
            return task

        def optimistic_update(self, t_id, from_, to, version):
            task.version = version + 1
            task.status = to
            return True

    class FakeThRepo:
        def by_task(self, t_id):
            return []

        def update_status(self, *a, **kw):
            pass

    class FakeApprRepo:
        def get(self, a_id):
            return approval

        def optimistic_update(self, a_id, from_, to, version):
            transitions.append((from_, to))
            return True

    monkeypatch.setattr(exec_service, "ExecTaskRepository", lambda db: FakeTaskRepo())
    monkeypatch.setattr(exec_service, "ExecTaskHostRepository", lambda db: FakeThRepo())
    monkeypatch.setattr(exec_service, "ApprovalRepository", lambda db: FakeApprRepo())
    monkeypatch.setattr(exec_service, "detect_sensitive", lambda db, c, sc, hc: (False, ""))
    monkeypatch.setattr(exec_service, "task_has_inprocess_agent", lambda db, t_id: False)
    monkeypatch.setattr(exec_service, "exec_dispatch", SimpleNamespace(delay=lambda t_id: None))

    result = exec_service.retry_task(FakeSession(), user, 2)

    assert result["status"] == "running"
    assert transitions == [("pending", "canceled")]


# ---------------------------------------------------------------- G10


def test_g10_list_tasks_scopes_non_admin_to_own(monkeypatch):
    seen = {}

    class FakeTaskRepo:
        def search(self, filters, page, size):
            seen.clear()
            seen.update(filters)
            return [], 0

    monkeypatch.setattr(exec_service, "ExecTaskRepository", lambda db: FakeTaskRepo())
    monkeypatch.setattr(exec_service, "_exec_task_out", lambda t: {"id": t.id})

    op = SimpleNamespace(id=7, is_admin=False, require_perm=lambda p: None)
    exec_service.list_tasks(None, op, None, None, None, None, None, None, 1, 10)
    assert seen["created_by"] == 7, "operator list must be scoped to own tasks (G10)"

    admin = SimpleNamespace(id=7, is_admin=True, require_perm=lambda p: None)
    exec_service.list_tasks(None, admin, None, None, None, None, None, None, 1, 10)
    assert "created_by" not in seen, "admin is allowed to see all tasks"