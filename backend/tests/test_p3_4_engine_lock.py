r"""P3-4b workflow engine + WS contract locks — @单元测试工程师 (lock-first, add-only).

Frozen contract: @架构 **P3-4b engine tuple v1.1** (seq2918) + **实施缝裁定** (seq2920)
+ **v1.2** (callback/attempt/recover, seq2924) + **v1.2.1** (waiting-timeout/payload-cap, seq2925)
+ **v1.2.2** (exec_task in-process dispatch via exec_service/_kick_off_exec, seq2935);
@需求 §27.2 full-scope ruling (seq2916/2922/2926); design `docs/architecture-phase23.md §13.1/§13.3`.

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
A1  openapi `paths` **>= 144** (142 + ws-token + callback) + no-shrink (`removed == []`);
    later add-only batches (P3-5) may extend the count — the EXACT current value is
    pinned only by `test_contract_openapi.py` (@架构 seq3051/seq3053)
A2  ws-token + callback URL keys present with correct methods
G1  migration: P3-4 edge (`a1b2c3d4e5f7` descends from `f2a3b4c5d6e7`) + single head
    that **descends from** `a1b2c3d4e5f7` (P3-5 may extend the chain; @架构 seq3051)
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
B9  waiting timeout: callback node w/ config.timeout_sec -> failed(reason=timeout) (never hangs)
B10 callback payload > 65536 B -> 422 `callback_payload_too_large` (not silently truncated)
B11 `exec_task` node (R-复用): REAL exec_task row built + node.exec_task_id stored
    (+ spy: 一期 exec 原语 called >=1, direct proof §27.2);
    row `success` -> node succeeded -> run succeeded
B12 `exec_task` node non-success terminal -> node failed -> `on_failure` branch; run failed
B13 `manual_approval` (R-复用): REAL approval_request built + node -> `waiting`
    (+ spy: 一期 approval 原语 called >=1);
    approved -> succeeded (resumes); rejected -> failed + `on_failure`
B14 cancel propagates to a node whose一期 exec_task is still `running` (D3):
    exec_task CANONICAL `canceled` (single l) via the perm-free一期 core +
    every `exec_task_host` row `canceled` (+ finished_at); node -> skipped; run cancelled
B14b cancel propagates to a sensitive `awaiting_approval` exec_task (D1/D3):
    exec_task -> `canceled` and its pending exec approval closed (no orphan);
    node -> skipped; run cancelled
B14c cancel landing DURING in-process dispatch (mechanism A, @架构 seq3012): the
    engine sets `node.exec_task_id` and dispatches in the SAME step, committing only
    at step end, so an external `cancel_run` in that window used to read
    `node.exec_task_id == NULL` (`workflow_service.py:493`), SKIP the exec_task and
    orphan it (live F RED). Fix = commit `node.exec_task_id` (node=running) BEFORE
    dispatch. Deterministic lock: the inner `exec_dispatch` seam runs the external
    cancel at dispatch time; no orphan allowed -> linked exec_task must be `canceled`
B15 `exec_task` sensitive command is gated (fail-closed, @架构 seq2957): a sensitive
    `command` -> REAL exec_task row with `sensitive_flag`/`approve_required`=1 +
    `awaiting_approval` + linked pending `exec` approval_request (never silently
    `running`); engine must not bypass the一期 exec sensitivity/approval linkage
B16 `manual_approval` released via the REAL一期 `approval_service.approve()` (the
    platform approval path, @代码reviewer seq2970/2972): `_approve_linkages` routes any
    non-`terminal` biz_type into `_approve_exec`, which `task_repo.get(biz_id)`
    fails for `biz_type="workflow"` -> `NotFoundError` -> `approve()` rollback.
    B13 decides the row directly and hides this; §27.2 needs the real path
B17 `manual_approval` decided via the REAL一期 `approval_service.reject()`
    (no crash; node failed + `on_failure`)
B18 UNKNOWN biz_type via the REAL一期 `approval_service.approve()` stays fail-closed
    (@需求 seq2977): raise -> `db.rollback()`, row persists `pending`, zero side
    effects. Pins the EXPLICIT `=="workflow"` guard form of (B) and blocks a future
    regression to a catch-all `else: no-op` (which would flip fail-closed to
    fail-open and silently approve an unrelated row)
B19 `exec_dispatch` aggregate finalize must NOT clobber a concurrent cancel
    (D2/§27.2 external-cancel convergence; @架构 seq3013, @需求 seq3008, @单元 seq3009):
    the一期 `app/tasks/exec_tasks.py` aggregate wrote `task.status`/`finished_at`
    unconditionally (no CAS, no `canceled` guard) while `agent_ws._maybe_finalize_task`
    and `scan_timeouts` ARE CAS-guarded. Since the engine host① dispatches in-process,
    an external `cancel_run` in the `running` window was overwritten back to `success`
    (live F RED). Implementation-neutral: once the linked exec_task is `canceled`, the
    dispatch aggregate must leave it `canceled`

WS close-code matrix (4401/4404) and frame `seq` monotonicity are asserted by live F
(@集成), per tuple G — not reproducible on the offline TestClient without a running driver.

Run (backend checkout, backend venv):
    python -m pytest tests/test_p3_4_engine_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib
import itertools
import re
import time

import pytest

from tests.openapi_baseline import M6_P3_4_KEYS

# R-FLAKE-1 (@架构 seq3043): `_seed_run` must NOT derive the workflow name from
# `id(definition)` — the address of a discarded inline dict literal can be reused
# by the next literal (GC-timing), colliding on the UNIQUE `workflow.name`. A
# process-local monotonic counter is deterministic and reproducible.
_WF_NAME_SEQ = itertools.count(1)


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


def test_a1_paths_count_at_least_144():
    """P3-4b landed 144; later add-only batches (P3-5) may add keys.

    Pin the LOWER BOUND here (batch lock, @架构 seq3051/seq3053) and keep the EXACT
    current value in `test_contract_openapi.py`. No-shrink against the FROZEN M6
    baseline key set (@架构 seq3057 layer ④) — NOT the current committed file, else a
    net-zero substitution would slip through.
    """
    paths = _openapi_paths()
    assert len(paths) >= 144, (
        f"P3-4b adds 2 URL keys (ws-token + callback) => paths >= 144 (142 + 2); "
        f"got {len(paths)}. WS itself is NOT in openapi."
    )
    removed = set(M6_P3_4_KEYS) - set(paths)
    assert not removed, (
        f"openapi keys must not shrink below the M6 baseline (@架构 seq3057): "
        f"removed={sorted(removed)}"
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


def _descends(rev: str | None, ancestor: str, revs: dict[str, str | None]) -> bool:
    seen: set[str] = set()
    while rev and rev not in seen:
        seen.add(rev)
        if rev == ancestor:
            return True
        rev = revs.get(rev)
    return False


def test_g1_migration_edge_p34_descends_from_p33_single_head():
    """Pin the P3-4 EDGE and require the single head to descend from it.

    The old form asserted the head IS `a1b2c3d4e5f7` (global head proxy), which a
    later add-only batch (P3-5) legitimately breaks. Batch locks pin their own edge;
    the next batch's rev is pinned by its own lock (@架构 seq3051/seq3053).
    """
    revs = _revision_graph()
    assert _P34_REV in revs, f"P3-4 rev {_P34_REV} missing from versions dir"
    assert revs.get(_P34_REV) == _P33_REV, (
        f"P3-4 edge: {_P34_REV} must descend directly from {_P33_REV}; "
        f"got {revs.get(_P34_REV)!r}"
    )
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    assert _descends(heads[0], _P34_REV, revs), (
        f"head {heads[0]!r} must descend from the P3-4 rev {_P34_REV} "
        "(a later add-only batch may extend the chain)"
    )


# ── offline SQLite harness ───────────────────────────────────────────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine, event  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

WF_TABLES = ("workflow", "workflow_version", "workflow_run", "workflow_node_run")
_CORE_TABLES = (
    "config_rule", "sys_audit_log", "sys_user", "exec_task", "exec_task_host",
    "approval_request", "approval_rule", "approval_record",
    "asset_group", "asset_host", "script", "script_version",
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
    # Offline PG sequences: exec_service._task_no / _approval_no call
    # `SELECT nextval('seq_…')`, which SQLite lacks. Provide a test-internal,
    # per-engine monotonic nextval (semantically equivalent; production ID
    # generation untouched) — @架构 seq2940 裁定③.
    _seq: dict[str, int] = {}

    def _nextval(name: str) -> int:
        _seq[name] = _seq.get(name, 0) + 1
        return _seq[name]

    def _register_nextval(dbapi_conn, _record) -> None:
        dbapi_conn.create_function("nextval", 1, _nextval)

    event.listen(engine, "connect", _register_nextval)
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

    wf = Workflow(name=f"wf-{next(_WF_NAME_SEQ)}", current_version=1, enabled=1)
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
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    definition = {"nodes": [
        {"key": "a", "type": "wait", "config": {"duration_sec": 3600, "timeout_sec": 1},
         "depends_on": [], "on_failure": ["c"]},
        _sleep("b", deps=["a"]),
        _sleep("c"),
    ]}
    rid = _seed_run(session, definition)
    eng.step(session, rid)  # a -> running (long wait, 1s timeout)
    time.sleep(1.2)         # let the 1s node timeout elapse
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
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    # a long `wait` keeps the node in `running` so the 0->1 attempt bump is observable
    rid = _seed_run(session, {"nodes": [
        {"key": "a", "type": "wait", "config": {"duration_sec": 3600}, "depends_on": []},
    ]})
    assert _node(session, rid, "a").attempt == 0
    eng.step(session, rid)
    session.expire_all()
    a = _node(session, rid, "a")
    session.refresh(a)
    assert a.status == "running" and a.attempt == 1, (
        f"entering running must set attempt 0->1; got status={a.status} attempt={a.attempt}"
    )


def test_b7_recover_runs_resumes_and_missing_exec_row_fails(env, monkeypatch):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    # no real driver thread may race the offline step loop while recover_runs runs
    monkeypatch.setattr(eng, "DRIVER_AUTOSTART", False, raising=False)
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


def test_b9_waiting_timeout_fails_not_hangs(env):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    rid = _seed_run(session, {"nodes": [
        {"key": "cb", "type": "callback", "config": {"timeout_sec": 1}, "depends_on": []},
    ]})
    for _ in range(5):
        session.expire_all()
        if _node(session, rid, "cb").status == "waiting":
            break
        eng.step(session, rid)
    assert _node(session, rid, "cb").status == "waiting", "callback node must block in `waiting`"
    time.sleep(1.2)
    status = _step_until_done(session, rid)
    n = _node(session, rid, "cb")
    session.refresh(n)
    assert n.status == "failed", (
        f"a waiting node past its timeout must fail (never hang forever); got {n.status}"
    )
    reason = ((n.output or {}).get("reason") or "") + (n.error or "")
    assert "timeout" in reason.lower(), (
        f"failure reason must record timeout; got output={n.output!r} error={n.error!r}"
    )
    assert status == "failed"


def test_b10_callback_payload_cap_422(env):
    session, set_flag = env
    set_flag(True)
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    rid = _seed_run(session, {"nodes": [
        {"key": "cb", "type": "callback", "config": {}, "depends_on": []},
    ]})
    for _ in range(5):
        session.expire_all()
        if _node(session, rid, "cb").status == "waiting":
            break
        eng.step(session, rid)
    token = ((_node(session, rid, "cb").output or {}).get("callback") or {}).get("token")
    assert token, "waiting callback node must expose a token"

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
            headers={"X-Callback-Token": token},
            json={"blob": "x" * 70000},
        )
        assert r.status_code == 422, (
            f"payload > 65536 B must be 422 (no silent truncation); got {r.status_code}: {r.text[:200]}"
        )
        assert "callback_payload_too_large" in r.text, (
            f"over-cap code must be `callback_payload_too_large`; got {r.text[:200]}"
        )
    finally:
        app.dependency_overrides.clear()


# ── B11/B12: exec_task node reuses the一期 exec primitive (R-复用 hard gate) ──
# Tuple D: `exec_task` carries config.host_ids + command|script_id; the engine
# MUST build a REAL `exec_task` row (never copy exec logic), store its id on the
# node, and follow that row's terminal status (step polls the DB). The一期
# executor injection seam is faked so dispatch never touches a real host.

def _fake_executor(monkeypatch) -> None:
    try:
        from app.services import executors as _ex  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return
    from unittest.mock import MagicMock  # noqa: PLC0415

    res = MagicMock()
    res.exit_code = 0
    res.stdout = ""
    res.stderr = ""
    res.to_dict.return_value = {"exit_code": 0, "stdout": "", "stderr": ""}
    fake = MagicMock()
    fake.name = "agent"
    fake.available = True
    fake.reason = ""
    fake.run.return_value = res
    fake.execute.return_value = res
    fake.dispatch.return_value = res
    monkeypatch.setattr(_ex, "build_executor", lambda name: fake, raising=False)


def _seed_host(session) -> int:
    from app.db.models.asset import Host  # noqa: PLC0415

    host = Host(hostname="h-exec", ip="10.9.9.9", connector="agent", status="online")
    session.add(host)
    session.commit()
    return host.id


def _exec_task_row(session, task_id: int):
    from app.db.models.exec import ExecTask  # noqa: PLC0415

    return session.get(ExecTask, task_id)


def _exec_task_host_rows(session, task_id: int):
    from app.db.models.exec import ExecTaskHost  # noqa: PLC0415

    return list(session.query(ExecTaskHost).filter_by(exec_task_id=task_id).all())


def _step_until_node_running(session, eng, rid: int, key: str, tries: int = 15):
    for _ in range(tries):
        session.expire_all()
        node = _node(session, rid, key)
        if node is not None and node.status == "running" and node.exec_task_id:
            return node
        eng.step(session, rid)
    session.expire_all()
    return _node(session, rid, key)


def _terminalize_exec_task(session, task_id: int, status: str) -> None:
    from app.db.models.exec import ExecTask  # noqa: PLC0415

    row = session.get(ExecTask, task_id)
    row.status = status
    session.commit()


def _exec_task_definition(host_id: int, *, on_failure=None) -> dict:
    node: dict = {
        "key": "e", "type": "exec_task",
        "config": {"host_ids": [host_id], "command": "true"}, "depends_on": [],
    }
    if on_failure:
        node["on_failure"] = on_failure
    return {"nodes": [node, _sleep("after-ok", deps=["e"]), _sleep("after-fail")]}


def _counting(fn, counts: dict, key: str):
    def _wrapped(*args, **kwargs):
        counts[key] = counts.get(key, 0) + 1
        return fn(*args, **kwargs)

    return _wrapped


def _install_reuse_spy(monkeypatch, eng) -> dict:
    """Count calls into the一期 exec/approval primitives (R-复用 direct proof).

    The 43ac527 lock only proved reuse *indirectly* (real row + build_executor);
    @需求 seq2944 upgraded "directly provable" to a §27.2 hard gate. Patching the
    *module-level* primitives survives a ``from … import y`` in the engine (the
    primitive body resolves these globals at call time). Counts only; call-through
    is preserved, so behaviour is unchanged.
    """
    counts: dict[str, int] = {"exec": 0, "approval": 0}
    targets = (
        ("app.services.exec_service", {
            "_task_no": "exec", "_kick_off_exec": "exec",
            "create_task": "exec", "_approval_no": "approval",
        }),
        ("app.services.approval_service", {"_approval_no": "approval"}),
    )
    for modname, names in targets:
        mod = _try(modname)
        if isinstance(mod, Exception):
            continue
        for name, key in names.items():
            fn = getattr(mod, name, None)
            if callable(fn):
                monkeypatch.setattr(mod, name, _counting(fn, counts, key), raising=False)
    return counts


def test_b11_exec_task_node_builds_and_waits(env, monkeypatch):
    session, _ = env
    _fake_executor(monkeypatch)
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    reuse = _install_reuse_spy(monkeypatch, eng)
    host_id = _seed_host(session)
    rid = _seed_run(session, _exec_task_definition(host_id))
    node = _step_until_node_running(session, eng, rid, "e")
    assert node.status == "running" and node.exec_task_id, (
        f"exec_task node must enter running with a stored exec_task_id; got "
        f"status={node.status} exec_task_id={node.exec_task_id}"
    )
    assert _exec_task_row(session, node.exec_task_id) is not None, (
        "R-复用 hard gate: engine must build a REAL exec_task row, not copy exec logic "
        f"(no row for exec_task_id={node.exec_task_id})"
    )
    assert reuse["exec"] >= 1, (
        "R-复用 direct proof (§27.2, @需求 seq2944): engine must CALL the一期 exec "
        "primitive (exec_service.create_task/_kick_off_exec/_task_no); none observed"
    )
    _terminalize_exec_task(session, node.exec_task_id, "success")
    assert _step_until_done(session, rid) == "succeeded", "exec success must drive run to succeeded"
    nodes = _nodes(session, rid)
    assert nodes["e"] == "succeeded", f"exec_task node must follow its row to succeeded; got {nodes}"


def test_b12_exec_task_failure_takes_on_failure_branch(env, monkeypatch):
    session, _ = env
    _fake_executor(monkeypatch)
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    host_id = _seed_host(session)
    rid = _seed_run(session, _exec_task_definition(host_id, on_failure=["after-fail"]))
    node = _step_until_node_running(session, eng, rid, "e")
    assert node.status == "running" and node.exec_task_id, (
        f"exec_task node must enter running with a stored exec_task_id; got {node.status!r}"
    )
    _terminalize_exec_task(session, node.exec_task_id, "failed")
    assert _step_until_done(session, rid) == "failed", "exec failure must drive run to failed"
    nodes = _nodes(session, rid)
    assert nodes["e"] == "failed", f"non-success exec terminal must fail the node; got {nodes}"
    assert nodes["after-fail"] == "succeeded", f"`on_failure` branch must run; got {nodes}"
    assert nodes["after-ok"] == "skipped", f"success-path downstream must be skipped; got {nodes}"


# ── B15: exec_task sensitive command gate (fail-closed) ──────────────────────
# @架构 seq2957: the engine reuses `_task_no`/`_kick_off_exec` but MUST NOT bypass
# the exec-layer safeguards — a sensitive `command` must NEVER silently become a
# `running` exec_task. The一期 `exec_service` marks sensitivity
# (`sensitive_flag`/`approve_required`) and links an `exec` approval, moving the
# task to `awaiting_approval` before any dispatch (US-06/US-09). The engine must
# retain this guarantee via a shared core (or an explicit scope exemption from
# @需求/@刘辉). This is a behaviour assertion, independent of the implementation
# symbol chosen, so it stays valid under either fix.

def _seed_sensitive_word(session, word: str) -> None:
    from app.db.models.notify import ConfigRule  # noqa: PLC0415

    session.add(ConfigRule(rule_key="exec_sensitive_word", rule_value={"words": [word]}))
    session.commit()


def _sensitive_exec_definition(host_id: int) -> dict:
    node: dict = {
        "key": "e", "type": "exec_task",
        "config": {"host_ids": [host_id], "command": "rm -rf /tmp/p34e"}, "depends_on": [],
    }
    return {"nodes": [node, _sleep("after-ok", deps=["e"])]}


def test_b15_sensitive_exec_task_is_gated_not_silently_running(env, monkeypatch):
    session, _ = env
    _fake_executor(monkeypatch)
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    host_id = _seed_host(session)
    _seed_sensitive_word(session, "rm -rf")
    rid = _seed_run(session, _sensitive_exec_definition(host_id))
    for _ in range(15):
        session.expire_all()
        node = _node(session, rid, "e")
        if node is not None and node.exec_task_id:
            break
        eng.step(session, rid)
    session.expire_all()
    node = _node(session, rid, "e")
    assert node is not None and node.exec_task_id, (
        f"sensitive exec_task node must build an exec_task row; got {node and node.status!r}"
    )
    row = _exec_task_row(session, node.exec_task_id)
    assert row is not None, "sensitive exec_task must build a REAL exec_task row"
    assert int(getattr(row, "sensitive_flag", 0) or 0) == 1, (
        "US-06/09 fail-closed: a sensitive `command` must set exec_task.sensitive_flag=1; "
        "the engine must not bypass the一期 exec sensitivity detection"
    )
    assert int(getattr(row, "approve_required", 0) or 0) == 1, (
        "sensitive exec_task must require approval (approve_required=1)"
    )
    assert row.status == "awaiting_approval", (
        "sensitive exec_task must NOT silently run: expected status 'awaiting_approval', "
        f"got {row.status!r} (bypasses the exec approval gate)"
    )
    from app.db.models.schedule import ApprovalRequest  # noqa: PLC0415

    ap = (
        session.query(ApprovalRequest)
        .filter_by(biz_type="exec", biz_id=row.id)
        .one_or_none()
    )
    assert ap is not None and ap.status == "pending", (
        "sensitive exec_task must link a pending `exec` approval_request"
    )
    session.expire_all()
    assert _run_status(session, rid) != "succeeded", (
        "run must not silently succeed around an unapproved sensitive exec_task"
    )


# ── B13: manual_approval reuses the一期 approval primitive (R-复用 hard gate) ─
# Tuple D: engine builds a REAL `approval_request` via the existing primitive,
# node -> `waiting` + `approval_id`; approve -> succeeded (run resumes),
# reject -> failed + `on_failure`.

def _approval_row(session, approval_id: int):
    from app.db.models.schedule import ApprovalRequest  # noqa: PLC0415

    return session.get(ApprovalRequest, approval_id)


def _step_until_node_waiting(session, eng, rid: int, key: str, tries: int = 15):
    for _ in range(tries):
        session.expire_all()
        node = _node(session, rid, key)
        if node is not None and node.status == "waiting":
            return node
        eng.step(session, rid)
    session.expire_all()
    return _node(session, rid, key)


def _decide_approval(session, approval_id: int, status: str) -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    row = _approval_row(session, approval_id)
    row.status = status
    row.decided_at = datetime.now(timezone.utc)
    session.commit()


def _approval_definition(*, on_failure=None) -> dict:
    node: dict = {"key": "ap", "type": "manual_approval", "config": {}, "depends_on": []}
    if on_failure:
        node["on_failure"] = on_failure
    return {"nodes": [node, _sleep("after-ok", deps=["ap"]), _sleep("after-fail")]}


def test_b13_manual_approval_blocks_then_releases(env, monkeypatch):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    reuse = _install_reuse_spy(monkeypatch, eng)
    # (i) approve -> node succeeded, run resumes downstream
    rid = _seed_run(session, _approval_definition())
    node = _step_until_node_waiting(session, eng, rid, "ap")
    assert node.status == "waiting", (
        f"manual_approval must block the node in `waiting`; got {node.status}"
    )
    assert node.approval_id, "manual_approval must store approval_id (reuse一期 primitive)"
    assert _approval_row(session, node.approval_id) is not None, (
        "R-复用 hard gate: engine must build a REAL approval_request row, not copy approval logic"
    )
    assert reuse["approval"] >= 1, (
        "R-复用 direct proof (§27.2, @需求 seq2944): engine must CALL the一期 approval "
        "primitive (its `_approval_no`); none observed"
    )
    _decide_approval(session, node.approval_id, "approved")
    assert _step_until_done(session, rid) == "succeeded", "approval must release the node"
    nodes = _nodes(session, rid)
    assert nodes["ap"] == "succeeded", f"approved node must continue as succeeded; got {nodes}"
    assert nodes["after-ok"] == "succeeded", f"approved path must continue downstream; got {nodes}"

    # (ii) reject -> node failed + `on_failure` branch
    rid2 = _seed_run(session, _approval_definition(on_failure=["after-fail"]))
    node2 = _step_until_node_waiting(session, eng, rid2, "ap")
    assert node2.status == "waiting" and node2.approval_id, (
        f"manual_approval must wait with an approval_id; got {node2.status!r}/{node2.approval_id!r}"
    )
    _decide_approval(session, node2.approval_id, "rejected")
    assert _step_until_done(session, rid2) == "failed", "rejection must fail the run"
    nodes2 = _nodes(session, rid2)
    assert nodes2["ap"] == "failed", f"rejected node must be failed; got {nodes2}"
    assert nodes2["after-fail"] == "succeeded", f"`on_failure` branch must run; got {nodes2}"
    assert nodes2["after-ok"] == "skipped", f"success-path downstream must be skipped; got {nodes2}"


# ── B16/B17: manual_approval release via the REAL一期 approval service ─────────
# @代码reviewer seq2970/2972: 一期 `approval_service._approve_linkages` routes any
# non-`terminal` biz_type into `_approve_exec`, whose `task_repo.get(biz_id)`
# returns None for `biz_type="workflow"` -> `NotFoundError` -> `approve()` rolls
# back and re-raises. B13 decides the approval row directly, so it cannot catch
# this. §27.2 requires the REAL platform approval path to release a workflow
# node; the fix may be a `workflow` branch in approval_service (frozen-behaviour
# change => @刘辉 scope) or a redesign — either way this observable must hold.

def _approval_service_or_fail():
    ap_svc = _try("app.services.approval_service")
    if isinstance(ap_svc, Exception):
        pytest.fail(f"P3-4b lock: approval_service unavailable: {ap_svc}")
    return ap_svc


def test_b16_manual_approval_approved_via_approval_service(env, monkeypatch):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    ap_svc = _approval_service_or_fail()
    rid = _seed_run(session, _approval_definition())
    node = _step_until_node_waiting(session, eng, rid, "ap")
    assert node is not None and node.status == "waiting" and node.approval_id, (
        f"manual_approval must reach `waiting` with an approval_id; got {node and node.status!r}"
    )
    try:
        ap_svc.approve(session, _U(), node.approval_id, "ok")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "一期 approval_service.approve() must release a workflow manual_approval; "
            f"raised {type(exc).__name__}: {exc} (biz_type routing drops 'workflow' "
            "into _approve_exec -> NotFoundError -> rollback)"
        )
    assert _step_until_done(session, rid) == "succeeded", (
        "approving via the platform approval service must resume the run"
    )
    nodes = _nodes(session, rid)
    assert nodes["ap"] == "succeeded" and nodes["after-ok"] == "succeeded", (
        f"approved workflow node must continue; got {nodes}"
    )


def test_b17_manual_approval_rejected_via_approval_service(env, monkeypatch):
    session, _ = env
    eng = _try("app.services.workflow_engine")
    if isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: workflow_engine unavailable: {eng}")
    ap_svc = _approval_service_or_fail()
    rid = _seed_run(session, _approval_definition(on_failure=["after-fail"]))
    node = _step_until_node_waiting(session, eng, rid, "ap")
    assert node is not None and node.status == "waiting" and node.approval_id, (
        f"manual_approval must reach `waiting` with an approval_id; got {node and node.status!r}"
    )
    try:
        ap_svc.reject(session, _U(), node.approval_id, "no")
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "一期 approval_service.reject() must decide a workflow manual_approval; "
            f"raised {type(exc).__name__}: {exc}"
        )
    assert _step_until_done(session, rid) == "failed", "rejection must fail the run"
    nodes = _nodes(session, rid)
    assert nodes["ap"] == "failed" and nodes["after-fail"] == "succeeded", (
        f"rejected workflow node must take `on_failure`; got {nodes}"
    )


# ── B18: unknown biz_type approve is fail-closed (pins the explicit (B) guard) ─
# @需求 seq2977 scope ruling: the (B) fix MUST be an explicit `=="workflow"` guard
# placed before the fall-through, so an UNKNOWN biz_type still reaches
# `_approve_exec` -> `task_repo.get(biz_id)` None -> `NotFoundError` -> `approve()`
# rollback (phase-1 fail-closed). A catch-all `else: return` (no-op) would flip this
# to fail-open and silently approve an unrelated row. This negative pin holds both
# before and after the (B) fix, blocking a regression to catch-all. It needs only
# the frozen phase-1 approval service (no engine), so it is GREEN from day one —
# the intended guard against the catch-all form, not an engine-absent failure.

# Deliberately far outside the exec_task id domain; B18 asserts no collision.
_UNKNOWN_BIZ_ID = 9_876_543_210


def _seed_unknown_approval(session, biz_type: str = "mystery") -> int:
    from app.db.models.schedule import ApprovalRequest  # noqa: PLC0415

    ap = ApprovalRequest(
        request_no=f"AP-LOCK-{biz_type}",
        biz_type=biz_type,
        biz_id=_UNKNOWN_BIZ_ID,
        title="lock: unknown biz_type fail-closed",
        requester_id=_U.id,
        status="pending",
    )
    session.add(ap)
    session.commit()
    return ap.id


def test_b18_unknown_biz_type_approve_is_fail_closed(env):
    session, _ = env
    ap_svc = _approval_service_or_fail()
    from app.core.exceptions import NotFoundError  # noqa: PLC0415
    from app.db.models.exec import ExecTask  # noqa: PLC0415
    from app.db.models.schedule import ApprovalRecord, ApprovalRequest  # noqa: PLC0415

    assert session.get(ExecTask, _UNKNOWN_BIZ_ID) is None, (
        "B18 premise (@代码reviewer seq2978 / @架构 seq2979): the unknown biz_type's "
        "`biz_id` must NOT collide with any `exec_task.id`. The fail-closed behaviour "
        "here is `_approve_exec`'s `task_repo.get(biz_id)` landing empty — NOT a "
        "biz_type gate. A colliding id would let `_approve_exec` advance that unrelated "
        "task regardless of biz_type (biz_id is globally unique with no relational tie "
        "to biz_type), making this lock vacuously pass."
    )
    ap_id = _seed_unknown_approval(session)
    with pytest.raises(NotFoundError):
        ap_svc.approve(session, _U(), ap_id, "ok")

    session.expire_all()
    row = session.get(ApprovalRequest, ap_id)
    assert row is not None and row.status == "pending", (
        "fail-closed (@需求 seq2977): approving an UNKNOWN biz_type must roll back and "
        f"leave the row `pending`; got {None if row is None else row.status!r} "
        "(a catch-all `else: no-op` would silently approve it => fail-open)"
    )
    assert row.approver_id is None and row.decided_at is None, (
        "fail-closed: approve must not persist approver_id/decided_at after rollback"
    )
    assert row.version == 0, (
        f"fail-closed: version must be unchanged after rollback; got {row.version}"
    )
    records = session.query(ApprovalRecord).filter_by(approval_id=ap_id).all()
    assert records == [], (
        "fail-closed: approve must write NO ApprovalRecord when the linkage raises; "
        f"found {[(r.action, r.operator_id) for r in records]}"
    )


# D3 (@架构 seq2986 / @代码reviewer seq2988): cancel must reuse a perm-free一期 exec
# core (mirroring `exec_service.stop_task`'s writable status domain
# ⊇ {created, running, awaiting_approval}); canonical status is `"canceled"`
# (single l — `"cancelled"` is NO LONGER tolerated), every `exec_task_host` row is
# marked `canceled` (+ finished_at), and a pending exec approval on an
# `awaiting_approval` task is closed (not orphaned).

def test_b14_cancel_propagates_to_running_exec_task(env, monkeypatch):
    session, set_flag = env
    set_flag(True)
    _fake_executor(monkeypatch)
    svc = _try("app.services.workflow_service")
    eng = _try("app.services.workflow_engine")
    if isinstance(svc, Exception) or isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: services unavailable: {svc if isinstance(svc, Exception) else eng}")
    host_id = _seed_host(session)
    rid = _seed_run(session, _exec_task_definition(host_id))
    node = _step_until_node_running(session, eng, rid, "e")
    assert node.status == "running" and node.exec_task_id, (
        f"need a running exec_task node to cancel; got {node.status!r}/{node.exec_task_id!r}"
    )
    svc.cancel_run(session, _U(), rid)
    session.expire_all()
    assert _run_status(session, rid) == "cancelled", "cancel must drive the run to cancelled"
    assert _node(session, rid, "e").status == "skipped", (
        "cancel must propagate: running node -> skipped"
    )
    row = _exec_task_row(session, node.exec_task_id)
    assert row is not None and row.status == "canceled", (
        "cancel must set the一期 exec_task to canonical `canceled` via the perm-free "
        "一期 core (single l; `cancelled` NOT accepted — D3 @架构 seq2986); got "
        f"{None if row is None else row.status!r}"
    )
    assert row.finished_at is not None, "cancel must stamp exec_task.finished_at"
    host_rows = _exec_task_host_rows(session, node.exec_task_id)
    assert host_rows and all(h.status == "canceled" for h in host_rows), (
        "cancel must mark every `exec_task_host` row `canceled` (D3); got "
        f"{[(h.id, h.status) for h in host_rows]}"
    )
    assert all(h.finished_at is not None for h in host_rows), (
        "cancel must stamp finished_at on cancelled `exec_task_host` rows"
    )


def test_b14b_cancel_awaiting_approval_exec_task_closes_pending_approval(env, monkeypatch):
    session, set_flag = env
    set_flag(True)
    _fake_executor(monkeypatch)
    svc = _try("app.services.workflow_service")
    eng = _try("app.services.workflow_engine")
    if isinstance(svc, Exception) or isinstance(eng, Exception):
        pytest.fail(f"P3-4b lock: services unavailable: {svc if isinstance(svc, Exception) else eng}")
    from app.db.models.schedule import ApprovalRequest  # noqa: PLC0415

    host_id = _seed_host(session)
    _seed_sensitive_word(session, "rm -rf")
    rid = _seed_run(session, _sensitive_exec_definition(host_id))
    node = _step_until_node_waiting(session, eng, rid, "e")
    assert node is not None and node.exec_task_id, (
        f"sensitive exec_task node must reach `waiting` with an exec_task; "
        f"got {node and node.status!r}/{node and node.exec_task_id!r}"
    )
    row = _exec_task_row(session, node.exec_task_id)
    assert row is not None and row.status == "awaiting_approval", (
        f"sensitive exec_task must be `awaiting_approval` before cancel; "
        f"got {None if row is None else row.status!r}"
    )
    ap = (
        session.query(ApprovalRequest)
        .filter_by(biz_type="exec", biz_id=row.id, status="pending")
        .one_or_none()
    )
    assert ap is not None, "sensitive exec_task must hold a pending exec approval before cancel"
    ap_id = ap.id
    svc.cancel_run(session, _U(), rid)
    session.expire_all()
    assert _run_status(session, rid) == "cancelled", "cancel must drive the run to cancelled"
    assert _node(session, rid, "e").status == "skipped", "cancel must skip the waiting node"
    row = _exec_task_row(session, node.exec_task_id)
    assert row is not None and row.status == "canceled", (
        "cancel must also cancel an `awaiting_approval` exec_task (D1 writable status "
        f"domain ⊇ {{created,running,awaiting_approval}}); got "
        f"{None if row is None else row.status!r}"
    )
    ap = _approval_row(session, ap_id)
    assert ap is not None and ap.status == "canceled", (
        "cancelling an awaiting_approval exec_task must close its pending approval "
        f"(reuse `_close_orphan_approval`, no orphan); got {None if ap is None else ap.status!r}"
    )


# ── B14c: cancel landing DURING in-process dispatch (mechanism A) ─────────────
# @架构 seq3012 mechanism A: `_create_exec_task` sets `node.exec_task_id` and calls
# `_kick_off_exec(in_process=True)` in the SAME step, committing only at `step()`
# end (`workflow_engine.py:219/231/401`). An external `cancel_run` in that window
# read `node.exec_task_id == NULL` (`workflow_service.py:493`, live F:
# `exec_task_id=null`), skipped the exec_task and left it orphaned. The fix commits
# `node.exec_task_id` (node=running) BEFORE dispatch. This lock is a deterministic
# proxy for "real slow executor + real driver thread": the inner `exec_dispatch`
# seam runs the external cancel exactly at dispatch time (own session), no threads.

def test_b14c_cancel_during_dispatch_leaves_no_orphan_exec_task(env, monkeypatch):
    session, set_flag = env
    set_flag(True)
    eng = _try("app.services.workflow_engine")
    svc = _try("app.services.workflow_service")
    ex = _try("app.services.exec_service")
    if isinstance(eng, Exception) or isinstance(svc, Exception) or isinstance(ex, Exception):
        pytest.fail(f"P3-4b lock: services unavailable: {eng}/{svc}/{ex}")
    host_id = _seed_host(session)
    rid = _seed_run(session, _exec_task_definition(host_id))
    captured: dict = {}

    def _dispatch_hook(task_id):
        # External cancel lands exactly at the dispatch point, in its own session.
        # Mechanism A: it only sees the exec_task if `node.exec_task_id` was
        # COMMITTED before dispatch (not merely set on the step session).
        captured["task_id"] = task_id
        s2 = _dbs.SessionLocal()
        try:
            svc.cancel_run(s2, _U(), rid)
            s2.commit()
        finally:
            s2.close()

    monkeypatch.setattr(ex, "exec_dispatch", _dispatch_hook)

    eng.step(session, rid)  # activate the exec node -> running
    eng.step(session, rid)  # build exec_task + dispatch (hook -> external cancel)
    session.expire_all()

    task_id = captured.get("task_id")
    assert task_id, "the dispatch seam must be reached with an exec_task id"
    assert _run_status(session, rid) == "cancelled", (
        "external cancel must drive the run to cancelled"
    )
    row = _exec_task_row(session, task_id)
    assert row is not None and row.status == "canceled", (
        "mechanism A (@架构 seq3012): a cancel landing during in-process dispatch "
        "must still reach the linked exec_task (commit `node.exec_task_id` before "
        f"dispatch) -> canonical `canceled` (no orphan); got "
        f"{None if row is None else row.status!r}"
    )


# ── B19: `exec_dispatch` aggregate must not clobber a concurrent cancel ───────
# @架构 seq3013 (承 @需求 seq3008 / @单元 seq3009): the一期 `exec_dispatch`
# aggregate finalize wrote `task.status`/`finished_at` UNCONDITIONALLY (no CAS, no
# `canceled` guard) -- unlike `agent_ws._maybe_finalize_task` / `scan_timeouts`,
# which are CAS-guarded. The P3-4b engine host① dispatches in-process via
# `_kick_off_exec(..., in_process=True)`, so an external `cancel_run` landing in the
# `running` window was overwritten back to `success` (live F RED). This lock pins the
# invariant implementation-neutrally: once a linked exec_task is `canceled`, the
# dispatch aggregate must NOT flip it back to a success/failed terminal.

def test_b19_exec_dispatch_aggregate_does_not_overwrite_canceled(env, monkeypatch):
    session, set_flag = env
    set_flag(True)
    et = _try("app.tasks.exec_tasks")
    if isinstance(et, Exception):
        pytest.fail(f"P3-4b lock: exec_tasks unavailable: {et}")
    from datetime import datetime, timezone  # noqa: PLC0415

    from sqlalchemy.orm import object_session  # noqa: PLC0415

    from app.db.models.exec import ExecTask  # noqa: PLC0415
    from app.services import exec_service  # noqa: PLC0415

    host_id = _seed_host(session)
    res = exec_service.create_exec_task_record(
        session, name="b19", kind="command", target_host_ids=[host_id],
        command="true", mode="batch", timeout_sec=300,
    )
    task_id = res["id"]
    session.expire_all()
    row = _exec_task_row(session, task_id)
    assert row is not None and row.status == "running", (
        f"B19 needs a `running` exec_task to dispatch; got {None if row is None else row.status!r}"
    )

    # Seams: the offline harness has no Redis semaphores / broker / WS.
    monkeypatch.setattr(et, "acquire_semaphore", lambda *a, **k: True)
    monkeypatch.setattr(et, "release_semaphore", lambda *a, **k: None)
    monkeypatch.setattr(et, "broadcast_sync", lambda *a, **k: None)

    def _fake_exec_then_cancel(task, th, content, timeout_sec, params):
        """Make this host terminal, then simulate a concurrent external cancel
        (separate session) landing BEFORE the aggregate finalize runs."""
        s1 = object_session(th)
        th.status = "success"
        th.exit_code = 0
        s1.commit()
        s2 = _dbs.SessionLocal()
        try:
            r = s2.get(ExecTask, task.id)
            r.status = "canceled"
            r.finished_at = datetime.now(timezone.utc)
            s2.commit()
        finally:
            s2.close()

    monkeypatch.setattr(et, "_execute_via_mock", _fake_exec_then_cancel)

    et.exec_dispatch(task_id)  # runs the terminal aggregate finalize
    session.expire_all()
    row = _exec_task_row(session, task_id)
    assert row is not None and row.status == "canceled", (
        "D2/§27.2 external-cancel invariant (@架构 seq3013): the `exec_dispatch` "
        "aggregate must NOT overwrite an already-`canceled` exec_task (needs CAS + "
        f"`canceled` guard); got {None if row is None else row.status!r}"
    )


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
