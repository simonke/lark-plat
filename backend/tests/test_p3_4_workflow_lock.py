r"""P3-4 编排 Playbook (workflow) contract locks — @单元测试工程师 (lock-first).

Frozen contract: @架构 **P3-4 开工令** (seq2891) + tuple shapes (seq2866) ;
design `docs/architecture-phase23.md §13` + `docs/api-design-v3.md §7.2` (commit M5 `e6712b9`) ;
requirements `§27.2` (@需求 seq2890, baseline v1.0).
Baseline = release **M5 = `e6712b9`** (master).

Symbol names = @架构 **canonical P3-4 tuple** (seq2894):
  app/db/models/workflow.py -> Workflow / WorkflowVersion / WorkflowRun / WorkflowNodeRun
                               RUN_STATUSES / NODE_TYPES / NODE_STATUSES / TERMINAL_RUN_STATUSES / TRIGGER_TYPES
  app/services/workflow_service.py -> module funcs list_workflows/create_workflow/get_workflow/
                               update_workflow/delete_workflow/create_version/list_versions/
                               rollback_workflow/run_workflow/list_runs/get_run/cancel_run/retry_run
  gate order = FEATURE FIRST (ticket pattern): service first line `_require_feature`, no require_perm in routes.

EXPECTED: clean **RED** until P3-4 backend lands (add-only); import-guarded so the
run reports assertion failures rather than collection errors. Offline only (temp SQLite;
no live PG/Redis; no migrations applied).

Scope of THIS lock (name-stable surface)
----------------------------------------
P1  9 permission codes ∈ seed `PERMISSION_TREE`; `workflow:retry` reuses `workflow:run` (NOT a code)
A1  openapi: 9 new URL keys present with correct methods (param names shape-matched)
A2  openapi `paths` **>= 144** (133 + 9 P3-4 keys + 2 P3-4b keys; URL-keyed, NOT
    operations) + no-shrink (`removed == []`); the EXACT current value is pinned only
    by `test_contract_openapi.py` (@架构 seq3051/seq3053)
M1  4 tables registered: workflow / workflow_version / workflow_run / workflow_node_run
M2  core columns per table (§13.2)
M3  module word-lists: RUN_STATUSES / NODE_TYPES / NODE_STATUSES / TERMINAL_RUN_STATUSES / TRIGGER_TYPES
C1  UNIQUE(workflow_id, version) on workflow_version
C2  UNIQUE(run_id, node_key) on workflow_node_run
F1  feature flag `feature.workflow` default **False** in `DEFAULT_CONFIG_RULES`
G1  migration: P3-4 edge (`a1b2c3d4e5f7` descends from `f2a3b4c5d6e7`) + single head
    that **descends from** `a1b2c3d4e5f7` (a later add-only batch may extend the chain;
    @架构 seq3051/seq3053)
T1  `WORKFLOW_TRANSITIONS` action-keyed: run start/succeed/fail/cancel allowed_from/target

Route-level behavioural locks (in-process TestClient, offline SQLite) — HTTP status / shape is
the contract, NOT function names:
R0  feature gate runs FIRST: flag off => 400 `feature disabled` for ANY caller (admin AND no-perm)
R1  flag on + missing perm => 403
R2  POST /workflows (workflow:add) -> 200 with id + name + current_version
R3  GET /workflows (workflow:list) -> 200 Page<Workflow> {list,total,page,size}
R4  POST /workflows/{id}/versions (workflow:version) -> 200; detail has `current_version`+`definition`
R5  definition with a cycle -> 422
R6  POST /workflows/{id}/run (workflow:run) -> 200 {run_id}; same Idempotency-Key -> same run_id
R7  GET /workflow-runs/{id} -> 200 structured {run, nodes[]}
R8  DELETE /workflows/{id} when referenced by a run -> 409
R9  definition over-limit (>cap nodes) -> 422 (baseline nodes<=100/edges<=500; freeze-fixed later)

Run (from the backend checkout, backend venv):
    python -m pytest tests/test_p3_4_workflow_lock.py -p no:cacheprovider -o addopts= -q
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


# ── P1: permission codes (seed PERMISSION_TREE) ──────────────────────────────

WORKFLOW_PERMS = {
    "workflow:list",
    "workflow:add",
    "workflow:edit",
    "workflow:del",
    "workflow:version",
    "workflow:rollback",
    "workflow:run",
    "workflow:view",
    "workflow:cancel",
}


def _perm_codes() -> set[str]:
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-4 lock: app.db.seed unavailable: {seed}")
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_workflow_permission_codes_registered():
    codes = _perm_codes()
    missing = WORKFLOW_PERMS - codes
    assert not missing, f"P3-4 permission codes missing from PERMISSION_TREE: {sorted(missing)}"
    assert "workflow:retry" not in codes, (
        "§13.3: `/workflow-runs/{id}/retry` REUSES `workflow:run`; do NOT add a `workflow:retry` code"
    )


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

# 9 URL keys (URL-keyed: GET+POST share one key). Param names matched by shape.
_WF = r"/api/v1/workflows"
_WF_ID = r"/api/v1/workflows/\{[^}]+\}"


def _wf_paths() -> dict[str, set[str]]:
    return {
        _WF: {"get", "post"},
        _WF_ID: {"get", "put", "delete"},
        _WF_ID + r"/versions": {"post", "get"},
        _WF_ID + r"/rollback": {"post"},
        _WF_ID + r"/run": {"post"},
        r"/api/v1/workflow-runs": {"get"},
        r"/api/v1/workflow-runs/\{[^}]+\}": {"get"},
        r"/api/v1/workflow-runs/\{[^}]+\}/cancel": {"post"},
        r"/api/v1/workflow-runs/\{[^}]+\}/retry": {"post"},
    }


_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def _committed_openapi_paths() -> dict:
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    p = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
    return json.loads(p.read_text(encoding="utf-8")).get("paths", {})


def test_a1_p3_4_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for pat, want in _wf_paths().items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in _METHODS}
        miss = want - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P3-4 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_at_least_144():
    """P3-4/P3-4b landed 144; later add-only batches (P3-5) may add keys.

    Batch lock pins the LOWER BOUND (@架构 seq3051/seq3053) and the global contract
    test pins the EXACT current value. No-shrink: every committed docs/openapi.json
    key must still be present at runtime (`removed == []`).
    """
    paths = _openapi_paths()
    assert len(paths) >= 144, (
        f"P3-4/P3-4b paths must be at least 144 (133 + 9 P3-4 + 2 P3-4b); got {len(paths)}. "
        "OpenAPI `paths` is URL-keyed; /workflows·/{id}·/{id}/versions·/{id}/rollback·/{id}/run "
        "· /workflow-runs·/{id}·/{id}/cancel·/{id}/retry = 9 keys, 13 ops; P3-4b adds "
        "GET /api/v1/workflow-runs/{id}/ws-token + POST …/callback/{node_key} "
        "(the WS endpoint itself is NOT in openapi)."
    )
    removed = set(_committed_openapi_paths()) - set(paths)
    assert not removed, (
        f"openapi keys must not shrink (later add-only batches may add, never remove): "
        f"removed={sorted(removed)}"
    )


# ── M1/M2/M3: SQLAlchemy tables, columns, word-lists ─────────────────────────

WF_TABLES = ("workflow", "workflow_version", "workflow_run", "workflow_node_run")
WF_COLUMNS = {
    "workflow": {"id", "name", "description", "current_version", "enabled", "created_by",
                 "created_at", "updated_at"},
    "workflow_version": {"id", "workflow_id", "version", "definition", "editor_id", "created_at"},
    "workflow_run": {"id", "workflow_id", "workflow_version", "status", "trigger_type",
                     "trigger_ref", "context", "started_at", "finished_at", "error", "created_by",
                     "created_at"},
    "workflow_node_run": {"id", "run_id", "node_key", "node_type", "status", "exec_task_id",
                          "approval_id", "attempt", "output", "error", "started_at", "finished_at"},
}
RUN_STATUSES = {"pending", "running", "succeeded", "failed", "cancelled"}
NODE_TYPES = {"exec_task", "manual_approval", "wait", "callback", "sleep"}
NODE_STATUSES = {"pending", "running", "succeeded", "failed", "skipped", "waiting"}
TERMINAL_RUN_STATUSES = {"succeeded", "failed", "cancelled"}
TRIGGER_TYPES = {"manual", "ticket", "schedule", "alert", "release"}


def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415  (register all models)
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-4 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_workflow_tables_registered():
    tables = _tables()
    missing = [t for t in WF_TABLES if t not in tables]
    assert not missing, (
        f"P3-4 must define {list(WF_TABLES)} (§13.2); missing {missing}"
    )


def test_m2_workflow_core_columns():
    tables = _tables()
    problems = []
    for name, want in WF_COLUMNS.items():
        t = tables.get(name)
        if t is None:
            problems.append(f"{name}: table missing")
            continue
        miss = want - set(t.columns.keys())
        if miss:
            problems.append(f"{name}: missing columns {sorted(miss)}")
    assert not problems, "P3-4 column contract: " + "; ".join(problems)


def test_m3_workflow_word_lists_in_models():
    mod = _try("app.db.models.workflow")
    if isinstance(mod, Exception):
        pytest.fail(f"P3-4 lock: app.db.models.workflow unavailable: {mod}")
    want = {
        "RUN_STATUSES": RUN_STATUSES,
        "NODE_TYPES": NODE_TYPES,
        "NODE_STATUSES": NODE_STATUSES,
        "TERMINAL_RUN_STATUSES": TERMINAL_RUN_STATUSES,
        "TRIGGER_TYPES": TRIGGER_TYPES,
    }
    problems = []
    for name, expect in want.items():
        got = set(getattr(mod, name, ()))
        if got != expect:
            problems.append(f"{name}: must == {sorted(expect)}, got {sorted(got)}")
    assert not problems, "P3-4 word-list contract (tuple seq2894): " + "; ".join(problems)


# ── C1/C2: uniqueness constraints ────────────────────────────────────────────

def _has_unique(table, cols: set[str]) -> bool:
    from sqlalchemy import UniqueConstraint  # noqa: PLC0415

    for cst in table.constraints:
        if isinstance(cst, UniqueConstraint) and {c.name for c in cst.columns} == cols:
            return True
    for ix in table.indexes:
        if ix.unique and {c.name for c in ix.columns} == cols:
            return True
    return False


def test_c1_workflow_version_unique():
    t = _tables().get("workflow_version")
    if t is None:
        pytest.fail("P3-4 lock: table `workflow_version` missing (EXPECTED RED until P3-4 lands)")
    assert _has_unique(t, {"workflow_id", "version"}), (
        "workflow_version must be UNIQUE(workflow_id, version) (§13.2)"
    )


def test_c2_node_run_unique():
    t = _tables().get("workflow_node_run")
    if t is None:
        pytest.fail("P3-4 lock: table `workflow_node_run` missing (EXPECTED RED until P3-4 lands)")
    assert _has_unique(t, {"run_id", "node_key"}), (
        "workflow_node_run must be UNIQUE(run_id, node_key) (§13.2)"
    )


# ── F1: feature flag default off ─────────────────────────────────────────────

def test_f1_feature_workflow_default_false():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-4 lock: app.db.seed unavailable: {seed}")
    entry = getattr(seed, "DEFAULT_CONFIG_RULES", {}).get("feature.workflow")
    assert entry is not None, "feature.workflow not seeded in DEFAULT_CONFIG_RULES"
    assert entry.get("value") is False, (
        f"feature.workflow default must be False; got {entry.get('value')!r}"
    )


# ── G1: migration single head descending from the P3-3 head ──────────────────

_VERSIONS_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "alembic" / "versions"
_P33_HEAD = "f2a3b4c5d6e7"
_P34_REV = "a1b2c3d4e5f7"


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
    """Pin the P3-4 EDGE + require the single head to descend from it.

    The old form used a global head proxy (`revs[head] == P3-3`), which a later
    add-only batch (P3-5) legitimately breaks (@架构 seq3051/seq3053).
    """
    revs = _revision_graph()
    assert _P33_HEAD in revs, f"P3-3 head {_P33_HEAD} missing from versions dir"
    assert _P34_REV in revs, f"P3-4 rev {_P34_REV} missing from versions dir"
    assert revs.get(_P34_REV) == _P33_HEAD, (
        f"P3-4 edge: {_P34_REV} must descend directly from {_P33_HEAD}; "
        f"got {revs.get(_P34_REV)!r}"
    )
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    assert _descends(heads[0], _P34_REV, revs), (
        f"head {heads[0]!r} must descend from the P3-4 rev {_P34_REV} "
        "(a later add-only batch may extend the chain)"
    )


# ── T1: service transition map ───────────────────────────────────────────────

_SERVICE_FNS = (
    "list_workflows", "create_workflow", "get_workflow", "update_workflow", "delete_workflow",
    "create_version", "list_versions", "rollback_workflow", "run_workflow",
    "list_runs", "get_run", "cancel_run", "retry_run",
)


def test_t1_workflow_service_functions_present():
    mod = _try("app.services.workflow_service")
    if isinstance(mod, Exception):
        pytest.fail(f"P3-4 lock: app.services.workflow_service unavailable: {mod}")
    missing = [fn for fn in _SERVICE_FNS if not callable(getattr(mod, fn, None))]
    assert not missing, (
        f"app.services.workflow_service must expose callables per tuple seq2894: missing {missing}"
    )


# ── R0–R8: route-level behavioural locks (offline TestClient) ────────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_CORE_TABLES = ("config_rule", "sys_audit_log", "sys_user", *WF_TABLES)


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


_DEF_ONE_NODE = {"nodes": [{"key": "a", "type": "sleep", "config": {"seconds": 1}, "depends_on": []}]}
_DEF_CYCLE = {"nodes": [
    {"key": "a", "type": "sleep", "config": {}, "depends_on": ["b"]},
    {"key": "b", "type": "sleep", "config": {}, "depends_on": ["a"]},
]}


@pytest.fixture()
def wf_client(tmp_path):
    """Yields ``(client, set_user, set_flag)``."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p34.db'}", future=True)
    Base.metadata.create_all(engine, tables=_core_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()

    prev_bind = getattr(_dbs.SessionLocal, "kw", {}).get("bind")
    _dbs.SessionLocal.configure(bind=engine)

    import app.main as main  # noqa: PLC0415
    from app.api.deps import CurrentUser, get_current_user  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    main.app.dependency_overrides[get_db] = lambda: (yield session)

    def set_user(perms, admin=False):
        user = CurrentUser(
            user_id=1, username="qa", is_admin=admin,
            permissions=list(perms), visible_group_ids=[],
        )
        main.app.dependency_overrides[get_current_user] = lambda: user
        return user

    def set_flag(on: bool):
        try:
            from app.db.models.notify import ConfigRule  # noqa: PLC0415

            row = session.query(ConfigRule).filter_by(rule_key="feature.workflow").one_or_none()
            if row is None:
                session.add(ConfigRule(rule_key="feature.workflow", rule_value={"value": on}))
            else:
                row.rule_value = {"value": on}
            session.commit()
        except Exception:  # noqa: BLE001
            pass

    try:
        yield TestClient(main.app), set_user, set_flag
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_r0_feature_gate_runs_first_400_for_any_caller(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(False)
    # admin (would pass any perm gate) still gets 400 because the FEATURE gate is first
    set_user([], admin=True)
    r = client.get("/api/v1/workflows")
    assert r.status_code == 400, (
        f"flag off + admin must be 400 `feature disabled` (feature gate FIRST); got {r.status_code}: {r.text}"
    )
    assert r.json().get("code") == 400
    # no-perm caller also gets 400 (NOT 403) — proves feature-before-permission order
    set_user([], admin=False)
    r2 = client.get("/api/v1/workflows")
    assert r2.status_code == 400, (
        f"flag off + no-perm caller must be 400, NOT 403 (feature gate FIRST); got {r2.status_code}: {r2.text}"
    )


def test_r1_flag_on_missing_perm_403(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user([], admin=False)
    r = client.get("/api/v1/workflows")
    assert r.status_code == 403, f"flag on + missing workflow:list must be 403; got {r.status_code}: {r.text}"


def test_r2_create_workflow(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add"], admin=True)
    r = client.post("/api/v1/workflows", json={"name": "wf1", "description": "d"})
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"id", "name", "current_version"} <= set(d), (
        f"created workflow must expose id/name/current_version; keys={sorted(d)}"
    )


def test_r3_list_workflows_page(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:list"], admin=True)
    r = client.get("/api/v1/workflows")
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"list", "total", "page", "size"} <= set(d), (
        f"GET /workflows must return Page<Workflow> {{list,total,page,size}} "
        f"(PageVO.items has JSON alias `list`, @架构 seq2896 / @需求 seq2897); keys={sorted(d)}"
    )
    assert isinstance(d["list"], list)


def _create_wf(client):
    r = client.post("/api/v1/workflows", json={"name": "wfx", "description": ""})
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_r4_add_version_then_detail_has_current_version_and_definition(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version", "workflow:view"], admin=True)
    wid = _create_wf(client)
    rv = client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": _DEF_ONE_NODE})
    assert rv.status_code == 200, rv.text
    rd = client.get(f"/api/v1/workflows/{wid}")
    assert rd.status_code == 200, rd.text
    d = rd.json().get("data") or {}
    assert "current_version" in d and "definition" in d, (
        f"detail must inline current_version + its definition (avoid a second /versions call); keys={sorted(d)}"
    )


def test_r5_definition_cycle_422(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version"], admin=True)
    wid = _create_wf(client)
    r = client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": _DEF_CYCLE})
    assert r.status_code == 422, (
        f"DAG cycle must be 422 (same rule as KB/CMDB cycles); got {r.status_code}: {r.text}"
    )


def test_r6_run_idempotent_by_idempotency_key(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version", "workflow:run"], admin=True)
    wid = _create_wf(client)
    assert client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": _DEF_ONE_NODE}).status_code == 200
    h = {"Idempotency-Key": "k1"}
    r1 = client.post(f"/api/v1/workflows/{wid}/run", headers=h, json={})
    assert r1.status_code == 200, r1.text
    rid1 = (r1.json().get("data") or {}).get("run_id")
    assert rid1 is not None, f"POST /workflows/{{id}}/run must return {{run_id}}; got {r1.json()!r}"
    r2 = client.post(f"/api/v1/workflows/{wid}/run", headers=h, json={})
    assert r2.status_code == 200, r2.text
    rid2 = (r2.json().get("data") or {}).get("run_id")
    assert rid2 == rid1, (
        f"same Idempotency-Key must NOT re-run (same run_id); got {rid1!r} vs {rid2!r}"
    )


def test_r7_run_detail_structured(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version", "workflow:run", "workflow:view"], admin=True)
    wid = _create_wf(client)
    assert client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": _DEF_ONE_NODE}).status_code == 200
    rid = (client.post(f"/api/v1/workflows/{wid}/run", headers={"Idempotency-Key": "k7"}, json={})
           .json().get("data") or {}).get("run_id")
    r = client.get(f"/api/v1/workflow-runs/{rid}")
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"run", "nodes"} <= set(d), (
        f"GET /workflow-runs/{{id}} must return structured {{run, nodes[]}}; keys={sorted(d)}"
    )
    assert isinstance(d["nodes"], list)
    for n in d["nodes"]:
        assert {"node_key", "node_type", "status"} <= set(n), (
            f"each run node must expose node_key/node_type/status; keys={sorted(n)}"
        )


def test_r8_delete_referenced_workflow_409(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version", "workflow:run", "workflow:del"], admin=True)
    wid = _create_wf(client)
    assert client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": _DEF_ONE_NODE}).status_code == 200
    assert client.post(f"/api/v1/workflows/{wid}/run", headers={"Idempotency-Key": "k8"}, json={}).status_code == 200
    r = client.delete(f"/api/v1/workflows/{wid}")
    assert r.status_code == 409, (
        f"deleting a workflow referenced by a run must be 409; got {r.status_code}: {r.text}"
    )


def test_r9_definition_over_limit_422(wf_client):
    client, set_user, set_flag = wf_client
    set_flag(True)
    set_user(["workflow:add", "workflow:version"], admin=True)
    wid = _create_wf(client)
    huge = {"nodes": [
        {"key": f"n{i}", "type": "sleep", "config": {}, "depends_on": []} for i in range(1001)
    ]}
    r = client.post(f"/api/v1/workflows/{wid}/versions", json={"definition": huge})
    assert r.status_code == 422, (
        f"definition exceeding node cap (baseline 100) must be 422; got {r.status_code}: {r.text}"
    )
