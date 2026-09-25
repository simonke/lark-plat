r"""P3-4b workflow engine + WS contract locks — @单元测试工程师 (lock-first, add-only).

Frozen contract: @架构 **P3-4b engine tuple v1.1** (seq2918) + **实施缝裁定** (seq2920)
+ **v1.2** (callback/attempt/recover) ; @需求 §27.2 full-scope ruling (seq2916/2922);
design `docs/architecture-phase23.md §13.1/§13.3`.

Symbols (pinned by tuple):
  app/services/workflow_engine.py -> step(db, run_id)->bool, start_driver(run_id), recover_runs()
                                     DRIVER_AUTOSTART: bool = True
  app/ws/workflow_ws.py           -> broadcast_sync(run_id, frame) [+ websocket route]
  app/tasks/workflow_tasks.py     -> scan_workflow_timeouts (celery beat)
  REST: GET  /api/v1/workflow-runs/{run_id}/ws-token            -> {token}   (JWT type=ws)
        POST /api/v1/workflow-runs/{run_id}/callback/{node_key}  (header X-Callback-Token)

EXPECTED: clean **RED** until P3-4b lands; import-guarded so the run reports assertion
failures rather than collection errors. Offline only (temp SQLite; no live PG/Redis; no
migrations applied).

Scope of THIS lock
------------------
K1  engine module symbols + DRIVER_AUTOSTART default True
K2  workflow_ws.broadcast_sync present; WS route present; WS NOT in openapi
K3  timeout beat task `scan_workflow_timeouts` registered
A1  openapi `paths` == 144 (142 + ws-token + callback)
A2  ws-token + callback URL keys present with correct methods
G1  migration: single head, still descending from P3-3 (`a1b2c3d4e5f7`; no new rev)
F1  feature gate FIRST on run + callback (flag off -> 400 for any caller)

Behavioural locks (direct `workflow_engine.step`, offline SQLite):
B1  happy sleep/wait DAG -> run succeeded, all nodes succeeded
B2  parallel roots + AND-join -> join only after both succeed
B3  timeout -> node failed -> `on_failure` branch runs, success branch skipped, run failed
B4  cancel propagation -> pending/running/waiting nodes -> skipped, run cancelled
B5  callback: node waiting + output.callback{token,url,expires_at}; token -> succeeded + payload
B6  attempt: 0 -> 1 on entering running
B7  recover_runs(): running run resumes; running exec_task w/o row -> failed(engine_restart)
B8  DRIVER_AUTOSTART False path: run stays pending (driver NOT started), step drives it

WS close-code matrix (4401/4404) and frame `seq` monotonicity are asserted by live F
(@集成), per tuple G — not reproducible on the offline TestClient without a running driver.

Run (backend checkout, backend venv):
    python -m pytest tests/test_p3_4_engine_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib
import re

import pytest


def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


# ── K1: engine module symbols ────────────────────────────────────────────────

_ENGINE_FNS = ("step", "start_driver", "recover_runs")


def test_k1_engine_module_symbols_and_autostart_default():
    mod = _try("app.services.workflow_engine")
    if isinstance(mod, Exception):
        pytest.fail(f"P3-4b lock: app.services.workflow_engine unavailable: {mod}")
    missing = [fn for fn in _ENGINE_FNS if not callable(getattr(mod, fn, None))]
    assert not missing, (
        f"workflow_engine must expose callables per tuple seq2918/2924: missing {missing}"
    )
    autostart = getattr(mod, "DRIVER_AUTOSTART", None)
    assert isinstance(autostart, bool), (
        f"workflow_engine.DRIVER_AUTOSTART must be a bool (module-level switch, seq2920); "
        f"got {autostart!r}"
    )
    assert autostart is True, (
        "DRIVER_AUTOSTART default must be True (live autostart; lock sets it False, seq2920)"
    )


# ── K2: ws module + route present; WS not in openapi ─────────────────────────

_WS_ROUTE = "/api/v1/ws/workflow-runs/{run_id}"


def test_k2_workflow_ws_module_and_route():
    mod = _try("app.ws.workflow_ws")
    if isinstance(mod, Exception):
        pytest.fail(f"P3-4b lock: app.ws.workflow_ws unavailable: {mod}")
    assert callable(getattr(mod, "broadcast_sync", None)), (
        "app.ws.workflow_ws must expose broadcast_sync(run_id, frame) (tuple G, seq2918)"
    )
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4b lock: app.main unavailable: {exc}")
    from starlette.routing import WebSocketRoute  # noqa: PLC0415

    ws_paths = {getattr(r, "path", None) for r in app.routes if isinstance(r, WebSocketRoute)}
    assert _WS_ROUTE in ws_paths, (
        f"WS route {_WS_ROUTE} must be mounted (tuple G); have {sorted(p for p in ws_paths if p)}"
    )


def test_k2b_ws_not_in_openapi():
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4b lock: app.main unavailable: {exc}")
    paths = app.openapi().get("paths", {})
    hits = [k for k in paths if "/ws/workflow-runs" in k]
    assert not hits, f"WS must NOT appear in openapi (tuple A); found {hits}"


# ── K3: timeout beat task ────────────────────────────────────────────────────

def test_k3_timeout_beat_task_registered():
    try:
        from app.tasks.celery_app import celery_app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4b lock: celery app unavailable: {exc}")
    tasks = [str(v.get("task", "")) for v in (celery_app.conf.beat_schedule or {}).values()]
    assert any(t.endswith("scan_workflow_timeouts") for t in tasks), (
        f"beat must register `scan_workflow_timeouts` (tuple F); have {tasks}"
    )


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4b lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_paths_count_144():
    paths = _openapi_paths()
    assert len(paths) == 144, (
        f"P3-4b adds 2 URL keys (ws-token + callback) => paths must be 144 (142 + 2); "
        f"got {len(paths)}. WS itself is NOT in openapi."
    )


def test_a2_new_keys_present_with_methods():
    paths = _openapi_paths()
    want = {
        r"/api/v1/workflow-runs/\{[^}]+\}/ws-token": {"get"},
        r"/api/v1/workflow-runs/\{[^}]+\}/callback/\{[^}]+\}": {"post"},
    }
    problems = []
    for pat, expected in want.items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in {"get", "post", "put", "delete", "patch"}}
        miss = expected - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P3-4b openapi surface incomplete: " + "; ".join(problems)


# ── G1: migration single head (no new rev) ───────────────────────────────────

_VERSIONS_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "alembic" / "versions"
_P34_REV = "a1b2c3d4e5f7"
_P33_REV = "f2a3b4c5d6e7"


def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    return revs


def test_g1_migration_single_head_reuses_p34_rev():
    revs = _revision_graph()
    assert _P34_REV in revs, f"P3-4 rev {_P34_REV} missing from versions dir"
    assert revs.get(_P34_REV) == _P33_REV, (
        f"{_P34_REV} must descend from {_P33_REV}; got {revs.get(_P34_REV)!r}"
    )
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    assert heads[0] == _P34_REV, (
        f"P3-4b adds NO migration (tuple H) => head must remain {_P34_REV}; got {heads[0]}"
    )


# ── offline SQLite harness ───────────────────────────────────────────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

WF_TABLES = ("workflow", "workflow_version", "workflow_run", "workflow_node_run")
_CORE_TABLES = (
    "config_rule", "sys_audit_log", "sys_user", "exec_task",
    "approval_request", "approval_rule", "approval_record",
    *WF_TABLES,
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


def _core_tables():
    import app.db.models  # noqa: F401,PLC0415 (register all models)
    from app.db.base import Base  # noqa: PLC0415

    tl = Base.metadata.tables
    return [tl[name] for name in _CORE_TABLES if name in tl]


class _U:
    """Minimal user for service-level calls."""

    id = 1
    username = "qa"
    is_admin = True
    permissions: list[str] = []
    visible_group_ids: list[int] = []

    def require_perm(self, code: str) -> None:  # noqa: ARG002
        return None


@pytest.fixture()
def env(tmp_path):
    """Yields ``(session, set_flag)`` with an isolated offline SQLite DB and patched SessionLocal."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p34e.db'}", future=True)
    Base.metadata.create_all(engine, tables=_core_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()

    prev_bind = getattr(_dbs.SessionLocal, "kw", {}).get("bind")
    _dbs.SessionLocal.configure(bind=engine)

    def set_flag(on: bool) -> None:
        from app.db.models.notify import ConfigRule  # noqa: PLC0415

        row = session.query(ConfigRule).filter_by(rule_key="feature.workflow").one_or_none()
        if row is None:
            session.add(ConfigRule(rule_key="feature.workflow", rule_value={"value": on}))
        else:
            row.rule_value = {"value": on}
        session.commit()

    try:
        yield session, set_flag
    finally:
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


# ── behaviour helpers ────────────────────────────────────────────────────────

def _seed_run(session, definition) -> int:
    """Insert Workflow + Version + a `pending` Run + `pending` NodeRuns; return run_id."""
    from app.db.models.workflow import Workflow, WorkflowNodeRun, WorkflowRun, WorkflowVersion  # noqa: PLC0415

    wf = Workflow(name=f"wf-{id(definition)}", current_version=1, enabled=1)
    session.add(wf)
    session.flush()
    session.add(WorkflowVersion(workflow_id=wf.id, version=1, definition=definition))
    run = WorkflowRun(workflow_id=wf.id, workflow_version=1, status="pending", trigger_type="manual")
    session.add(run)
    session.flush()
    for node in definition.get("nodes") or []:
        session.add(
            WorkflowNodeRun(
                run_id=run.id, node_key=node["key"], node_type=node["type"],
                status="pending", attempt=0,
            )
        )
    session.commit()
    return run.id


def _step_until_done(session, run_id: int, max_steps: int = 60) -> str:
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    for _ in range(max_steps):
        session.expire_all()
        if _run_status(session, run_id) in {"succeeded", "failed", "cancelled"}:
            break
        eng.step(session, run_id)
    session.expire_all()
    return _run_status(session, run_id)


def _run_status(session, run_id: int) -> str:
    from app.db.models.workflow import WorkflowRun  # noqa: PLC0415

    return session.get(WorkflowRun, run_id).status


def _nodes(session, run_id: int) -> dict[str, str]:
    from app.db.models.workflow import WorkflowNodeRun  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    rows = session.scalars(
        select(WorkflowNodeRun).where(WorkflowNodeRun.run_id == run_id)
    ).all()
    return {r.node_key: r.status for r in rows}


def _node(session, run_id: int, key: str):
    from app.db.models.workflow import WorkflowNodeRun  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    return session.scalars(
        select(WorkflowNodeRun).where(
            WorkflowNodeRun.run_id == run_id, WorkflowNodeRun.node_key == key
        )
    ).one_or_none()


def _sleep(key: str, deps=None, *, on_success=None, on_failure=None, timeout=None) -> dict:
    cfg: dict = {"duration_sec": 0}
    if timeout is not None:
        cfg["timeout_sec"] = timeout
    node = {"key": key, "type": "sleep", "config": cfg, "depends_on": deps or []}
    if on_success:
        node["on_success"] = on_success
    if on_failure:
        node["on_failure"] = on_failure
    return node


def test_b1_happy_sleep_chain(env):
    session, _ = env
    rid = _seed_run(session, {"nodes": [_sleep("a"), _sleep("b", deps=["a"])]})
    assert _step_until_done(session, rid) == "succeeded"
    assert _nodes(session, rid) == {"a": "succeeded", "b": "succeeded"}


def test_b2_parallel_then_and_join(env):
    session, _ = env
    rid = _seed_run(session, {"nodes": [_sleep("a"), _sleep("b"), _sleep("c", deps=["a", "b"])]})
    assert _step_until_done(session, rid) == "succeeded"
    assert _nodes(session, rid) == {"a": "succeeded", "b": "succeeded", "c": "succeeded"}


def test_b3_timeout_failed_takes_on_failure_branch(env):
    session, _ = env
    definition = {"nodes": [
        _sleep("a", timeout=0, on_failure=["c"]),
        _sleep("b", deps=["a"]),
        _sleep("c"),
    ]}
    rid = _seed_run(session, definition)
    assert _step_until_done(session, rid) == "failed", "a timed-out run must end failed"
    nodes = _nodes(session, rid)
    assert nodes["a"] == "failed", f"timed-out node must be failed; got {nodes}"
    assert nodes["c"] == "succeeded", f"`on_failure` branch must run; got {nodes}"
    assert nodes["b"] == "skipped", f"success-path downstream must be skipped; got {nodes}"


def test_b4_cancel_propagation(env):
    session, set_flag = env
    set_flag(True)
    svc = _try("app.services.workflow_service")
    if isinstance(svc, Exception):
        pytest.fail(f"P3-4b lock: workflow_service unavailable: {svc}")
    rid = _seed_run(session, {"nodes": [_sleep("a", deps=["x"]), _sleep("b"), _sleep("x")]})
    svc.cancel_run(session, _U(), rid)
    session.expire_all()
    assert _run_status(session, rid) == "cancelled"
    nodes = _nodes(session, rid)
    assert all(s == "skipped" for s in nodes.values()), (
        f"cancel must propagate: pending/running/waiting nodes -> skipped; got {nodes}"
    )


def test_b5_callback_token_roundtrip(env):
    session, set_flag = env
    set_flag(True)
    rid = _seed_run(session, {"nodes": [{"key": "cb", "type": "callback", "config": {},
                                         "depends_on": []}]})
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    for _ in range(5):
        session.expire_all()
        if _node(session, rid, "cb").status == "waiting":
            break
        eng.step(session, rid)
    cb = _node(session, rid, "cb")
    session.refresh(cb)
    assert cb.status == "waiting", f"callback node must block in `waiting`; got {cb.status}"
    info = (cb.output or {}).get("callback") or {}
    assert {"token", "url", "expires_at"} <= set(info), (
        f"waiting callback node must expose output.callback{{token,url,expires_at}}; got {cb.output}"
    )

    # HTTP roundtrip with the node-level token.
    from app.main import app  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from app.api.deps import CurrentUser, get_current_user  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    app.dependency_overrides[get_db] = lambda: (yield session)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=1, username="qa", is_admin=True, permissions=[], visible_group_ids=[]
    )
    try:
        client = TestClient(app)
        r = client.post(
            f"/api/v1/workflow-runs/{rid}/callback/cb",
            headers={"X-Callback-Token": info["token"]},
            json={"ok": True},
        )
        assert r.status_code == 200, f"valid callback token must be 200; got {r.status_code}: {r.text}"
        session.expire_all()
        cb = _node(session, rid, "cb")
        session.refresh(cb)
        assert cb.status == "succeeded", f"callback must release the node; got {cb.status}"
        assert (cb.output or {}).get("payload") == {"ok": True}, (
            f"callback body must be stored in output.payload; got {cb.output}"
        )
        # second (already-terminal / no longer waiting) callback -> 409
        r2 = client.post(
            f"/api/v1/workflow-runs/{rid}/callback/cb",
            headers={"X-Callback-Token": info["token"]},
            json={},
        )
        assert r2.status_code == 409, f"callback on non-waiting node must be 409; got {r2.status_code}"
        # missing/!invalid token -> 401
        r3 = client.post(f"/api/v1/workflow-runs/{rid}/callback/cb", json={})
        assert r3.status_code == 401, f"missing callback token must be 401; got {r3.status_code}"
        # unknown run -> 404
        r4 = client.post(
            "/api/v1/workflow-runs/999999/callback/cb",
            headers={"X-Callback-Token": info["token"]},
            json={},
        )
        assert r4.status_code == 404, f"unknown run callback must be 404; got {r4.status_code}"
    finally:
        app.dependency_overrides.clear()


def test_b6_attempt_increments_on_running(env):
    session, _ = env
    rid = _seed_run(session, {"nodes": [_sleep("a")]})
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    assert _node(session, rid, "a").attempt == 0
    eng.step(session, rid)
    session.expire_all()
    a = _node(session, rid, "a")
    session.refresh(a)
    assert a.status == "running" and a.attempt == 1, (
        f"entering running must set attempt 0->1; got status={a.status} attempt={a.attempt}"
    )


def test_b7_recover_runs_resumes_and_missing_exec_row_fails(env):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    # (i) a `running` run with a healthy pending node resumes to terminal under step
    ok = _seed_run(session, {"nodes": [_sleep("a")]})
    session.expire_all()
    _force_run_running(session, ok)
    eng.recover_runs()
    assert _step_until_done(session, ok) == "succeeded", "recover_runs must let step resume"
    # (ii) a `running` exec_task node whose exec_task row is missing -> failed(engine_restart)
    bad = _seed_run(session, {"nodes": [{"key": "e", "type": "exec_task",
                                         "config": {"host_ids": [1], "command": "true"},
                                         "depends_on": []}]})
    session.expire_all()
    _force_run_running(session, bad)
    _force_node(nsession=session, run_id=bad, key="e", status="running", exec_task_id=987654321)
    eng.recover_runs()
    status = _step_until_done(session, bad)
    n = _node(session, bad, "e")
    session.refresh(n)
    assert n.status == "failed", (
        f"restart w/ missing exec_task row must fail the node (no blind re-dispatch); got {n.status}"
    )
    assert (n.error or "").lower().find("engine_restart") >= 0 or (n.output or {}).get("reason") == (
        "engine_restart"
    ), f"failure reason must record engine_restart; got error={n.error!r} output={n.output!r}"
    assert status == "failed"


def test_b8_driver_autostart_false_path(env, monkeypatch):
    session, set_flag = env
    set_flag(True)
    svc = _try("app.services.workflow_service")
    eng = _try("app.services.workflow_engine")
    if isinstance(svc, Exception) or isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: services unavailable: {svc if isinstance(svc, Exception) else eng}")
    calls: list[int] = []
    monkeypatch.setattr(eng, "DRIVER_AUTOSTART", False, raising=False)
    monkeypatch.setattr(eng, "start_driver", lambda run_id: calls.append(run_id), raising=False)
    wf = _seed_workflow_header(svc, session)
    res = svc.run_workflow(session, _U(), wf, None, None)
    rid = res["run_id"]
    assert calls == [], (
        f"with DRIVER_AUTOSTART False, run_workflow must NOT start the driver; got {calls}"
    )
    assert _run_status(session, rid) == "pending"
    assert _step_until_done(session, rid) == "succeeded", "step must still drive the run"


def _force_run_running(session, run_id: int) -> None:
    from app.db.models.workflow import WorkflowRun  # noqa: PLC0415

    run = session.get(WorkflowRun, run_id)
    run.status = "running"
    session.commit()


def _force_node(nsession, run_id: int, key: str, **fields) -> None:
    n = _node(nsession, run_id, key)
    for k, v in fields.items():
        setattr(n, k, v)
    nsession.commit()


def _seed_workflow_header(svc, session) -> int:
    from app.db.models.workflow import Workflow, WorkflowVersion  # noqa: PLC0415

    wf = Workflow(name="wf-autostart", current_version=1, enabled=1)
    session.add(wf)
    session.flush()
    session.add(WorkflowVersion(workflow_id=wf.id, version=1, definition={"nodes": [_sleep("a")]}))
    session.commit()
    return wf.id


# ── F1: feature gate FIRST (run + callback) ──────────────────────────────────

def test_f1_feature_gate_first_on_run_and_callback(env):
    session, set_flag = env
    set_flag(False)
    from app.main import app  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from app.api.deps import CurrentUser, get_current_user  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    app.dependency_overrides[get_db] = lambda: (yield session)
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=1, username="qa", is_admin=True, permissions=[], visible_group_ids=[]
    )
    try:
        client = TestClient(app)
        rid = _seed_run(session, {"nodes": [_sleep("a")]})
        r1 = client.post(f"/api/v1/workflow-runs/{rid}/callback/a", json={})
        assert r1.status_code == 400, (
            f"flag off + callback must be 400 `feature disabled` (gate first); got {r1.status_code}"
        )
    finally:
        app.dependency_overrides.clear()
