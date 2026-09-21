"""P2-SS SS-5: an ssh host reaches the executor orchestration on the real
dispatch route, and the frozen gate order is preserved.

Frozen routing (架构 seq2185 / backend seq2212; route 可达口径 corrected by
reviewer seq2218 / 架构 seq2219):

* Offline route reachability goes through the **create path only**:
  ``POST /exec/tasks`` -> ``_kick_off_exec`` (broker unavailable -> ``except`` ->
  in-process ``exec_dispatch``) -> ``exec_tasks.py:160`` ssh guard.
* The **approval-resume** path (``approval_service`` ``exec_dispatch.delay``
  inside ``try/except: pass``) is **not** reachable offline, so it is NOT used as
  route evidence here and is registered as deferred (real-env "C").

The executor is resolved via the module-attribute seam
``app.services.executors.build_executor`` (never a top-level from-import), so
monkeypatching the seam must take effect. Gate order:
``approval -> sensitivity -> executor.exec() -> exec_log``.

SS-5 A① assertion 口径 (架构 seq2219):
* ``approve_required=0`` + non-sensitive -> approval gate is a **skip**, the
  sensitivity gate passes, exec is called; assert "applicable gates precede
  exec", not "approval gate is always called";
* ``approve_required=1`` + already approved + non-sensitive -> approval gate
  **passes**, then sensitivity, then exec;
* sensitive command -> gate **blocks**, exec NOT called, ``"warn"`` log written;
* degraded (paramiko missing) -> gates still run first, exec returns degraded,
  a degraded ``exec_log`` row with ``paramiko not installed`` is written.

All offline: SQLite, ``get_redis`` -> None, celery broker shimmed in
``conftest.exec_env``. No real SSH (``paramiko`` deferred to the release phase).
"""

from __future__ import annotations

import uuid

import pytest

_EXEC_TASKS = "/api/v1/exec/tasks"


class _FakeExecutor:
    """Fake executor used as the injected seam value."""

    name = "ssh"

    def __init__(self, *, ok: bool = True, raises: BaseException | None = None):
        self.available = ok
        self.reason = None if ok else "paramiko not installed"
        self.calls = 0
        self.raises = raises

    def check(self, host):
        return {"ok": self.available, "latency_ms": None, "detail": "fake"}

    def exec(self, *args, **kwargs):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return {"ok": self.available, "detail": "fake-ran"}


class _OrderProbe:
    """Records the orchestration order and the return of each gate."""

    def __init__(self, monkeypatch):
        import app.services.executors.orchestrator as orch

        self.order: list[str] = []
        self.gate_results: dict[str, object] = {}
        self._orch = orch
        self._real = {
            "approval": orch._approval_gate,
            "sensitivity": orch._sensitivity_gate,
            "log": orch._write_log,
        }

        def _wrap(tag, fn):
            def inner(*args, **kwargs):
                self.order.append(tag)
                result = fn(*args, **kwargs)
                self.gate_results[tag] = result
                return result

            return inner

        monkeypatch.setattr(orch, "_approval_gate", _wrap("approval", self._real["approval"]))
        monkeypatch.setattr(orch, "_sensitivity_gate", _wrap("sensitivity", self._real["sensitivity"]))
        monkeypatch.setattr(orch, "_write_log", _wrap("log", self._real["log"]))


def _seed_task(env, *, executor="ssh", approve_required=0, approval_id=None,
               command="echo hi", status="running"):
    """Seed an ExecTask + one ExecTaskHost directly (bypasses POST/nextval)."""
    from app.db.models import ExecTask, ExecTaskHost

    em = env["session"]
    task = ExecTask(
        task_no=f"T-{uuid.uuid4().hex[:8]}",
        name="ss5",
        kind="command",
        command=command,
        target_host_ids={"ids": [1]},
        status=status,
        created_by=1,
        approve_required=approve_required,
        approval_id=approval_id,
    )
    em.add(task)
    em.commit()
    th = ExecTaskHost(
        exec_task_id=task.id, host_id=1, hostname="host1", ip="10.0.0.1",
        executor=executor, status="pending",
    )
    em.add(th)
    em.commit()
    return task.id, th.id


def _add_approval(env, status):
    from app.db.models import ApprovalRequest

    em = env["session"]
    approval = ApprovalRequest(
        request_no=f"AP-{uuid.uuid4().hex[:8]}", biz_type="exec", biz_id=0,
        title="t", reason="r", requester_id=1, sensitive_hit="x", status=status,
    )
    em.add(approval)
    em.commit()
    return approval.id


# ------------------------------------------------ route reachability (create)

def test_ssh_host_reaches_executor_via_route(exec_env, monkeypatch):
    """POST /exec/tasks (create path) for an ssh host must reach (not
    short-circuit) the executor and leave an ``exec_log`` row."""
    env = exec_env
    env["set_user"](perms={"exec:task:run"})
    hid = env["seed_host"](1, connector="ssh")

    fake = _FakeExecutor(ok=True)
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    resp = env["client"].post(
        _EXEC_TASKS,
        json={"name": "ss5", "kind": "command", "command": "echo hi",
              "target_host_ids": [hid]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    task_id = body["data"]["id"]

    assert fake.calls == 1, "ssh host must reach the executor, not short-circuit"

    from app.db.models import ExecLog, ExecTaskHost

    em = env["session"]
    em.expire_all()
    th = em.query(ExecTaskHost).filter_by(exec_task_id=task_id).one()
    assert th.executor == "ssh"
    assert th.status == "success"
    assert th.exit_code == 0
    logs = em.query(ExecLog).filter_by(task_host_id=th.id).all()
    assert logs, "exec_log row must be written on the ssh path"
    assert any(l.level == "info" and "[executor:ssh]" in l.content for l in logs)


# ------------------------------------------------------ gate order / wording

def test_gate_order_approve_required_0_skip_then_exec(exec_env, monkeypatch):
    """approve_required=0 + non-sensitive: the approval gate is a SKIP, the
    sensitivity gate passes, then exec -> log. Assert the applicable gates
    precede exec (not that the approval gate is always called)."""
    env = exec_env
    env["set_user"](perms={"exec:task:run"})
    env["seed_host"](1, connector="ssh")

    probe = _OrderProbe(monkeypatch)

    class _Rec(_FakeExecutor):
        def exec(self, *args, **kwargs):
            probe.order.append("exec")
            return super().exec(*args, **kwargs)

    fake = _Rec(ok=True)
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    resp = env["client"].post(
        _EXEC_TASKS,
        json={"name": "ss5", "kind": "command", "command": "echo hi",
              "target_host_ids": [1]},
    )
    assert resp.status_code == 200, resp.text
    assert fake.calls == 1
    assert probe.order == ["approval", "sensitivity", "exec", "log"]
    # approval gate was evaluated but returned skip (None) because not required
    assert probe.gate_results["approval"] is None
    assert probe.gate_results["sensitivity"] is None


def test_gate_order_approve_required_1_approved_then_exec(exec_env, monkeypatch):
    """approve_required=1 + already approved + non-sensitive: the approval gate
    PASSES (returns None), then sensitivity, then exec -> log."""
    env = exec_env
    env["seed_host"](1, connector="ssh")
    approval_id = _add_approval(env, status="approved")
    task_id, th_id = _seed_task(env, approve_required=1, approval_id=approval_id)

    probe = _OrderProbe(monkeypatch)

    class _Rec(_FakeExecutor):
        def exec(self, *args, **kwargs):
            probe.order.append("exec")
            return super().exec(*args, **kwargs)

    fake = _Rec(ok=True)
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    env["exec_tasks"].exec_dispatch(task_id)

    assert fake.calls == 1
    assert probe.order == ["approval", "sensitivity", "exec", "log"]
    assert probe.gate_results["approval"] is None  # approved -> passes
    assert probe.gate_results["sensitivity"] is None


def test_ssh_unavailable_still_reaches_executor_and_logs_degraded(exec_env, monkeypatch):
    """available=False must NOT short-circuit: the gates run first, exec is still
    called (and degrades), and a degraded log with the reason is written."""
    env = exec_env
    env["set_user"](perms={"exec:task:run"})
    env["seed_host"](1, connector="ssh")

    probe = _OrderProbe(monkeypatch)
    fake = _FakeExecutor(
        ok=False,
        raises=NotImplementedError("ssh executor unavailable: paramiko not installed"),
    )
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    resp = env["client"].post(
        _EXEC_TASKS,
        json={"name": "ss5", "kind": "command", "command": "echo hi",
              "target_host_ids": [1]},
    )
    assert resp.status_code == 200, resp.text
    task_id = resp.json()["data"]["id"]

    assert fake.calls == 1, "degraded ssh executor must still be invoked"
    assert probe.order[:2] == ["approval", "sensitivity"]
    assert "log" in probe.order

    from app.db.models import ExecLog, ExecTaskHost

    em = env["session"]
    em.expire_all()
    th = em.query(ExecTaskHost).filter_by(exec_task_id=task_id).one()
    assert th.status == "failed"
    assert th.exit_code == 1
    logs = em.query(ExecLog).filter_by(task_host_id=th.id).all()
    assert any(
        l.level == "error" and "paramiko not installed" in l.content for l in logs
    )


# --------------------------------------------------------- gate short-circuits

def test_approval_gate_blocks_before_exec(exec_env, monkeypatch):
    """A task whose approval is still pending must be blocked before exec(),
    with a ``warn`` log (拦下, not skip)."""
    env = exec_env
    approval_id = _add_approval(env, status="pending")
    task_id, th_id = _seed_task(env, approve_required=1, approval_id=approval_id)

    fake = _FakeExecutor(ok=True)
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    env["exec_tasks"].exec_dispatch(task_id)

    assert fake.calls == 0, "pending approval must gate exec()"
    from app.db.models import ExecLog

    em = env["session"]
    em.expire_all()
    logs = em.query(ExecLog).filter_by(task_host_id=th_id).all()
    assert any(l.level == "warn" and "awaiting approval" in l.content for l in logs)
    assert not any(
        l.level == "info" and "[executor:" in (l.content or "") for l in logs
    ), "a blocked task must not emit an executor run log (fail-closed, G1 seq2441)"


def test_sensitivity_gate_blocks_before_exec(exec_env, monkeypatch):
    """A command matching a sensitive rule must be blocked before exec(), with a
    ``warn`` log."""
    env = exec_env
    from app.db.models import ConfigRule

    em = env["session"]
    em.add(ConfigRule(rule_key="exec_sensitive_word", rule_value={"words": ["rm -rf"]}))
    em.commit()
    task_id, th_id = _seed_task(env, command="rm -rf /")

    fake = _FakeExecutor(ok=True)
    monkeypatch.setattr("app.services.executors.build_executor", lambda name: fake)

    env["exec_tasks"].exec_dispatch(task_id)

    assert fake.calls == 0, "sensitive command must gate exec()"
    from app.db.models import ExecLog

    em.expire_all()
    logs = em.query(ExecLog).filter_by(task_host_id=th_id).all()
    assert any(l.level == "warn" and "sensitive operation" in l.content for l in logs)
    assert not any(
        l.level == "info" and "[executor:" in (l.content or "") for l in logs
    ), "a blocked task must not emit an executor run log (fail-closed, G1 seq2441)"


def test_agent_host_path_is_untouched(exec_env):
    """The additive branch is guarded by executor=='ssh': an agent host does not
    go through run_exec (regression guard for the B' additivity claim)."""
    env = exec_env
    task_id, th_id = _seed_task(env, executor="agent")

    import app.services.executors.orchestrator as orch

    calls = {"n": 0}
    real = orch.run_exec

    def _spy(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    # ``_run_ssh_executor`` does ``from ...orchestrator import run_exec`` at call
    # time, so patching the orchestrator attribute is what the ssh branch picks up.
    orch.run_exec = _spy
    try:
        env["exec_tasks"].exec_dispatch(task_id)
    finally:
        orch.run_exec = real

    assert calls["n"] == 0, "agent hosts must not enter the ssh orchestration"
