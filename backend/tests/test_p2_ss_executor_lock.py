"""P2-SS (P2-4 executor extension) skeleton contract locks — @单元测试工程师.

Frozen interface tuple: 架构 seq2185 (授权 @刘辉 seq2184). Baseline = master
`6e8c353` (branch off `p2-ss-executor`; backend tree ≡ `aed07ad`, zero drift).
This batch is **schema-free / add-only / offline-fake only**:
  - `app/services/executors/base.py`  Executor Protocol: `check(host)->{ok,latency_ms,detail}`, `exec(...)`
  - `app/services/executors/agent_executor.py`  wraps the existing agent path (semantics ≡)
  - `app/services/executors/ssh_executor.py`  **lazy** `paramiko`; missing ⇒
        `available=False, reason="paramiko not installed"` (no hard dependency)
  - `asset_service.connectivity_check` ssh branch routed through the executor
        (replaces the "ssh not implemented" degraded string)
  - degraded routing `config_rule executor.ssh_fallback` (bool, **default false**, add-only)
  - new add-only paths (107 -> 109):
        `GET  /assets/hosts/{host_id}/executors` -> `{available:[...], active, reason}`
        `PUT  /assets/hosts/{host_id}/connector` -> connector ∈ {agent, ssh}
  - permission `asset:host:executor` (reuses `asset:host:edit`) in seed PERMISSION_TREE
  - `/monitor/*` stays 19; migration single head stays `e8a1b2c3d4f5`; no credential echo
  - equivalence (SS-5, 架构 seq2193/seq2197/seq2199) —「等价」:
        B′ structural same-source: the ssh orchestration reuses the *same* agent-path
        symbols (`exec_service.detect_sensitive`, `ExecLogRepository.append`), agent
        code untouched; A① gate order approval->sensitivity->exec->exec_log; A② the
        exec_log writer signature/fields; A③ `check()` degradation.
        The orchestration core is `executors/orchestrator.py::run_exec`, entered on
        the real dispatch route (`exec_tasks.exec_dispatch` -> `_run_ssh_executor`).
    C (explicit limitation, NOT assumed equivalent): WS frame equivalence — no
    additively-reusable shared frame constructor is asserted here (deferred, real
    SSH / agent.exe / paramiko on D: drive). Must not be read as "path unchanged
    therefore equivalent".

EXPECTED: all pins RED until the `p2-ss-executor` branch lands. Import guards keep
RED clean (no collection errors). Run from the backend checkout:
    python -m pytest tests/test_p2_ss_executor_lock.py -p no:cacheprovider -q

Evidence boundary (hard): skeleton = offline pure fake, NO real SSH; real SSH /
`agent.exe` build / `paramiko` install (D drive) are deferred and must not be claimed.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


# ── import guards (clean RED instead of collection errors) ───────────────────

def _try(mod: str, *names: str):
    try:
        m = importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return (None, exc) if not names else tuple([None] * len(names) + [exc])
    got = tuple(getattr(m, n, None) for n in names)
    return got if names else m


def _require(value, what: str):
    if value is None:
        pytest.fail(f"P2-SS lock: {what} not available yet (EXPECTED RED until p2-ss-executor lands)")


def _module(kind: str):
    mod = _try(f"app.services.executors.{kind}")
    if isinstance(mod, Exception):
        pytest.fail(f"P2-SS lock: app.services.executors.{kind} unavailable: {mod}")
    return mod


def _executor_instance(mod):
    """Best-effort resolve an executor object from a module (class or singleton)."""
    for name in ("SSHExecutor", "SshExecutor", "AgentExecutor", "Executor"):
        cls = getattr(mod, name, None)
        if isinstance(cls, type):
            for args in ((), (None,)):
                try:
                    return cls(*args)
                except Exception:  # noqa: BLE001
                    continue
    for name in ("ssh_executor", "SSH_EXECUTOR", "agent_executor", "AGENT_EXECUTOR", "executor"):
        obj = getattr(mod, name, None)
        if obj is not None and not isinstance(obj, type):
            return obj
    return None


def _check_keys(obj, host=None):
    res = obj.check(host)
    assert isinstance(res, dict), f"check(host) must return a dict, got {type(res)!r}"
    return set(res)


# ── S1: executors package + base Protocol ────────────────────────────────────

def test_s1_base_executor_protocol_members():
    base = _module("base")
    proto = getattr(base, "Executor", None)
    _require(proto, "executors.base.Executor")
    assert hasattr(proto, "check"), "Executor Protocol must declare check(host)"
    assert hasattr(proto, "exec"), "Executor Protocol must declare exec(...)"


def test_s1_agent_executor_present():
    agent = _module("agent_executor")
    obj = _executor_instance(agent)
    _require(obj, "agent_executor executor object")
    assert callable(getattr(obj, "check", None)), "agent executor must expose check(host)"


# ── S2: ssh executor is lazy / degraded, never a hard dependency ─────────────

def test_s2_ssh_executor_has_no_top_level_paramiko_import():
    mod = _module("ssh_executor")
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    top: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top.add(node.module.split(".")[0])
    assert "paramiko" not in top, (
        "paramiko must be imported lazily (inside a function), not at module top level "
        f"(seq2185: no hard dependency); top-level imports={sorted(top)}")
    assert re.search(r"\bparamiko\b", src), "ssh_executor should reference paramiko lazily"


def test_s2_ssh_executor_degraded_when_paramiko_absent():
    mod = _module("ssh_executor")
    obj = _executor_instance(mod)
    _require(obj, "ssh_executor executor object")
    if importlib.util.find_spec("paramiko") is None:
        assert getattr(obj, "available", None) is False, (
            "ssh executor.available must be False when paramiko is not installed")
        assert str(getattr(obj, "reason", "")) == "paramiko not installed", (
            "ssh executor.reason must be 'paramiko not installed' when paramiko is absent; "
            f"got {getattr(obj, 'reason', None)!r}")
    else:  # paramiko present in this environment
        assert getattr(obj, "available", None) is True


def test_s2_check_returns_frozen_keys_no_secret_echo():
    agent = _module("agent_executor")
    obj = _executor_instance(agent)
    _require(obj, "agent_executor executor object")
    keys = _check_keys(obj, host=None)
    assert keys == {"ok", "latency_ms", "detail"}, (
        f"executor.check(host) keys must be exactly {{ok,latency_ms,detail}} (seq2185); got {sorted(keys)}")
    leaked = {"password", "secret", "token", "client_secret", "private_key", "passphrase"}
    assert not (keys & leaked), f"executor.check must never echo credentials: {sorted(keys & leaked)}"


# ── C1: degraded routing flag default false ──────────────────────────────────

def test_c1_ssh_fallback_flag_defaults_false():
    try:
        from app.db import seed  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-SS lock: app.db.seed unavailable: {exc}")
    rules = getattr(seed, "DEFAULT_CONFIG_RULES", None)
    _require(rules, "seed.DEFAULT_CONFIG_RULES")
    assert "executor.ssh_fallback" in rules, (
        "config_rule 'executor.ssh_fallback' must be registered (add-only, default false)")
    value = rules["executor.ssh_fallback"]
    if isinstance(value, dict):
        value = value.get("value", value)
    assert value is False, f"executor.ssh_fallback default must be False; got {value!r}"


# ── S3: connectivity_check ssh branch routed through executor ────────────────

def test_s3_connectivity_check_uses_executor_not_placeholder():
    src = inspect.getsource(_module_asset_service())
    assert "ssh connector check not implemented" not in src, (
        "connectivity_check must route the ssh branch through the executor "
        "(old 'ssh not implemented' placeholder must be gone)")
    assert "executors" in src or "executor" in src, (
        "asset_service must reference the executor layer for the ssh branch")


def _module_asset_service():
    mod = _try("app.services.asset_service")
    if isinstance(mod, Exception):
        pytest.fail(f"P2-SS lock: app.services.asset_service unavailable: {mod}")
    return mod


# ── A1: openapi runtime surface (107 -> 109; /monitor stays 19) ──────────────

def _openapi_paths():
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-SS lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_paths_count_109_and_monitor_19():
    paths = _openapi_paths()
    monitor = [p for p in paths if "/monitor" in p]
    # P2-SS added paths 107->109. Later batches (P3) add more, so assert the
    # P2-SS floor holds rather than pinning the absolute global count (the
    # per-batch locks assert their own exact value).
    assert len(paths) >= 109, (
        f"openapi paths must be >= 109 after P2-SS (2 new URL keys); got {len(paths)}")
    # P5 supersession (tuple v1->r2 seq3332): P5 add-only adds 2 monitor URL keys
    # (/monitor/alerts/aggregate, /monitor/alerts/{alert_id}/ai/rca) => 19 -> 21.
    # Assert no regression below the P2-MA floor (monotonic).
    assert len(monitor) >= 19, f"/monitor/* must not regress below 19; got {len(monitor)}"


def _path_entry(paths, regex: str):
    return next((p for p in paths if re.fullmatch(regex, p)), None)


def test_a1_executors_and_connector_paths_present():
    paths = _openapi_paths()
    ex = _path_entry(paths, r"/api/v1/assets/hosts/\{[^}]+\}/executors")
    co = _path_entry(paths, r"/api/v1/assets/hosts/\{[^}]+\}/connector")
    assert ex is not None and "get" in paths[ex], "GET /assets/hosts/{host_id}/executors missing"
    assert co is not None and "put" in paths[co], "PUT /assets/hosts/{host_id}/connector missing"


def test_a1_connector_body_enum_agent_ssh():
    paths = _openapi_paths()
    co = _path_entry(paths, r"/api/v1/assets/hosts/\{[^}]+\}/connector")
    _require(co, "PUT /connector path")
    op = paths[co].get("put", {})
    body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
    ref = body.get("$ref")
    if ref:
        spec = _openapi()
        body = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    props = body.get("properties", {})
    assert "connector" in props, f"PUT /connector body must have a 'connector' field; got {sorted(props)}"
    enum = props["connector"].get("enum")
    assert enum is not None and set(enum) == {"agent", "ssh"}, (
        f"connector must be constrained to {{agent,ssh}}; got {enum!r}")


def _openapi():
    from app.main import app  # noqa: PLC0415

    return app.openapi()


# ── P1: permission point registered ─────────────────────────────────────────

def _walk_perms(tree, acc):
    for node in tree:
        acc.add(node[0])
        children = node[5] if len(node) > 5 else []
        if children:
            _walk_perms(children, acc)


def test_p1_permission_point_asset_host_executor():
    try:
        from app.db import seed  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-SS lock: app.db.seed unavailable: {exc}")
    acc: set[str] = set()
    _walk_perms(getattr(seed, "PERMISSION_TREE", []), acc)
    assert "asset:host:executor" in acc, (
        "permission point 'asset:host:executor' must be registered in PERMISSION_TREE")


# ── M1: schema-free batch ⇒ migration single head unchanged ──────────────────

def _versions_dir() -> Path:
    import app  # noqa: PLC0415

    return Path(app.__file__).resolve().parent.parent / "alembic" / "versions"


def _revisions() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for f in _versions_dir().glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(None|["\']([^"\']*)["\'])', text, re.M)
        if not rev:
            continue
        d = None
        if down:
            d = None if down.group(1) == "None" else down.group(2)
        out.append((rev.group(1), d))
    return out


def test_m1_single_head_unchanged_e8a1b2c3d4f5():
    revs = _revisions()
    _require(revs, "alembic revisions")
    by_rev = dict(revs)
    downs = {d for _, d in revs if d}
    heads = {r for r, _ in revs if r not in downs}
    assert len(heads) == 1, f"alembic must have exactly one head; got {sorted(heads)}"
    # P2-SS is explicitly schema-free (seq2185) so it did not move the head. A
    # later, separate batch (P3 ticket/kb) legitimately appends a migration, so
    # per the note below we assert the close-out revision stays ON the single
    # head chain rather than pinning it as the only head.
    head = next(iter(heads))
    chain: set[str] = set()
    cur: str | None = head
    while cur and cur not in chain:
        chain.add(cur)
        cur = by_rev.get(cur)
    assert "e8a1b2c3d4f5" in chain, (
        f"P2 close-out e8a1b2c3d4f5 must stay on the single head chain; "
        f"head={head!r}, chain={sorted(chain)}")


# ── SS-5 (等价): B′ structural same-source + A behaviour (offline fakes) ─────
# 架构 seq2193/seq2197 (B′ additive reuse, no agent-code change) / seq2199
# (degrade decided inside the orchestrator; route does not short-circuit).
# Unit scope = orchestrator internals; route-level hit is @集成测试工程师.

def _orchestrator():
    mod = _try("app.services.executors.orchestrator")
    if isinstance(mod, Exception):
        pytest.fail(f"P2-SS lock: app.services.executors.orchestrator unavailable: {mod}")
    return mod


def test_eq_b1_sensitivity_gate_reuses_agent_detector(monkeypatch):
    """B′: orchestrator sensitivity gate calls the SAME symbol as the agent path."""
    orch = _orchestrator()
    from app.services import exec_service  # noqa: PLC0415

    seen: dict = {}

    def spy(db, command, content, host_count):
        seen["called"] = (command, content, host_count)
        return (False, "")

    monkeypatch.setattr(exec_service, "detect_sensitive", spy)
    task = SimpleNamespace(approve_required=False, command="ls -l", approval_id=None)
    reason = orch._sensitivity_gate(None, task, "ls -l", 1)
    assert reason is None, f"non-sensitive command must pass the gate; got {reason!r}"
    assert "called" in seen, (
        "orchestrator._sensitivity_gate must reuse app.services.exec_service.detect_sensitive "
        "(the agent-path symbol); the patched spy was not invoked")


def test_eq_b2_write_log_reuses_agent_exec_log_writer(monkeypatch):
    """B′/A②: exec_log is written through the SAME repository as the agent path,
    with the identical (task_host_id, seq, level, content) call shape."""
    orch = _orchestrator()
    from app.repositories import ExecLogRepository  # noqa: PLC0415

    captured: dict = {}

    def spy_append(self, task_host_id, seq, level, content):
        captured.update(task_host_id=task_host_id, seq=seq, level=level, content=content)

    monkeypatch.setattr(ExecLogRepository, "max_seq", lambda self, th_id: 4)
    monkeypatch.setattr(ExecLogRepository, "append", spy_append)

    class FakeDB:
        committed = False

        def commit(self):
            self.committed = True

    db = FakeDB()
    th = SimpleNamespace(id=7)
    orch._write_log(db, th, "info", "hello")
    assert captured == {"task_host_id": 7, "seq": 5, "level": "info", "content": "hello"}, captured
    assert db.committed is True, "exec_log write must commit on the same session"


def test_eq_a1_gate_order_before_exec(monkeypatch):
    """A①: approval -> sensitivity -> executor.exec() -> exec_log, in that order."""
    orch = _orchestrator()
    order: list[str] = []

    monkeypatch.setattr(orch, "_approval_gate", lambda db, task: (order.append("approval"), None)[1])
    monkeypatch.setattr(
        orch, "_sensitivity_gate",
        lambda db, task, content, hc: (order.append("sensitivity"), None)[1])
    monkeypatch.setattr(orch, "_write_log", lambda db, th, level, content: order.append("log"))

    class FakeExec:
        def exec(self, **kw):
            order.append("exec")
            return {"ok": True, "detail": "done"}

    task = SimpleNamespace(approve_required=False)
    th = SimpleNamespace(id=1, executor="ssh")
    res = orch.run_exec(None, task, th, "cmd", executor=FakeExec())
    assert order == ["approval", "sensitivity", "exec", "log"], order
    assert res.get("ok") is True


def test_eq_a1b_gate_failure_skips_exec_but_logs(monkeypatch):
    """A①: a failing approval gate short-circuits sensitivity AND exec, still logs."""
    orch = _orchestrator()
    order: list[str] = []
    logs: list = []

    monkeypatch.setattr(orch, "_approval_gate", lambda db, task: "awaiting approval")
    monkeypatch.setattr(
        orch, "_sensitivity_gate",
        lambda db, task, content, hc: (order.append("sensitivity"), None)[1])
    monkeypatch.setattr(orch, "_write_log", lambda db, th, level, content: logs.append((level, content)))

    class FakeExec:
        def exec(self, **kw):
            order.append("exec")
            return {"ok": True}

    task = SimpleNamespace(approve_required=True)
    th = SimpleNamespace(id=1, executor="ssh")
    res = orch.run_exec(None, task, th, "cmd", executor=FakeExec())
    assert order == [], "approval gate must run before sensitivity/exec; neither may fire"
    assert logs and logs[0][0] == "warn", f"skip must be recorded as a warn exec_log; got {logs}"
    assert not any(
        level == "info" and "[executor:" in content for level, content in logs
    ), "a blocked task must not emit an executor run log (fail-closed, G1 seq2441)"
    assert res.get("skipped") is True


def test_eq_a3_degraded_exec_still_logs(monkeypatch):
    """A③: an unavailable executor degrades (no crash) and still writes an exec_log."""
    orch = _orchestrator()
    logs: list = []

    monkeypatch.setattr(orch, "_approval_gate", lambda db, task: None)
    monkeypatch.setattr(orch, "_sensitivity_gate", lambda db, task, content, hc: None)
    monkeypatch.setattr(orch, "_write_log", lambda db, th, level, content: logs.append((level, content)))

    class DegradedExec:
        def exec(self, **kw):
            raise NotImplementedError("ssh executor unavailable: paramiko not installed")

    task = SimpleNamespace(approve_required=False)
    th = SimpleNamespace(id=1, executor="ssh")
    res = orch.run_exec(None, task, th, "cmd", executor=DegradedExec())
    assert res.get("degraded") is True, res
    assert logs and logs[-1][0] == "error", f"degradation must be logged at error level; got {logs}"


def test_eq_a_reach_orchestrator_wired_on_dispatch_route():
    """Reachability (reviewer (a), non-dead-code): the orchestration is entered on
    the real dispatch route, guarded by `th.executor == "ssh"`."""
    et = _try("app.tasks.exec_tasks")
    if isinstance(et, Exception):
        pytest.fail(f"P2-SS lock: app.tasks.exec_tasks unavailable: {et}")
    assert hasattr(et, "_run_ssh_executor"), "exec_tasks must expose the additive ssh branch"
    src = inspect.getsource(et)
    assert "run_exec" in src, "dispatch route must call executors.orchestrator.run_exec"
    assert 'th.executor == "ssh"' in src, (
        "the ssh orchestration branch must be guarded by th.executor == 'ssh' "
        "(agent path stays the default)")


def test_eq_b3_approval_gate_real_logic(monkeypatch):
    """B′/A① (架构 seq2216/seq2219): the approval gate's real skip/through/block
    logic, evaluated before the executor — not monkeypatched away. Same
    `ApprovalRepository.get` seam as the agent path; literal `approved`."""
    orch = _orchestrator()
    calls: dict = {}

    class FakeRepo:
        def __init__(self, db):
            pass

        def get(self, aid):
            calls["get"] = aid
            status = calls.get("status")
            return None if status == "missing" else SimpleNamespace(status=status)

    monkeypatch.setattr(orch, "ApprovalRepository", FakeRepo)
    assert orch.APPROVED == "approved", (
        "orchestrator approval literal must be the agent-path literal 'approved'")

    # approve_required False -> skip (gate not applicable)
    assert orch._approval_gate(None, SimpleNamespace(approve_required=False, approval_id=None)) is None

    # approve_required True + approved -> pass
    calls["status"] = "approved"
    assert orch._approval_gate(None, SimpleNamespace(approve_required=True, approval_id=5)) is None
    assert calls.get("get") == 5, "gate must look up the task's approval_id"

    # approve_required True + pending -> blocked
    calls["status"] = "pending"
    assert orch._approval_gate(None, SimpleNamespace(approve_required=True, approval_id=5)) == "awaiting approval"

    # approve_required True + missing approval -> blocked
    calls["status"] = "missing"
    assert orch._approval_gate(None, SimpleNamespace(approve_required=True, approval_id=5)) == "awaiting approval"


def test_eq_b4_sensitivity_gate_blocks(monkeypatch):
    """B′/A①: a sensitive command is blocked by the gate (same detector symbol),
    so `exec()` never runs."""
    orch = _orchestrator()
    from app.services import exec_service  # noqa: PLC0415

    monkeypatch.setattr(
        exec_service, "detect_sensitive",
        lambda db, command, content, host_count: (True, "sensitive word: rm"))
    task = SimpleNamespace(approve_required=False, command="rm -rf /")
    reason = orch._sensitivity_gate(None, task, "rm -rf /", 1)
    assert reason is not None and "sensitive" in reason.lower(), reason


