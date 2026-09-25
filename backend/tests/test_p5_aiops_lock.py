r"""P5 (AIOps E3/E4/E5) contract locks — @单元 lock-first, add-only.

Frozen contract: @架构 **P5 tuple v1 -> r2** (seq3327 / seq3332) + @需求 **§29 v1.0**
(seq3333). Base = release **M9 `1960c29890a2c9762c68cc9ce236104436d06ebc`** (master).

Pinned surface (tuple v1->r2):
  A E3 ingestion   : published article -> chunk -> `LLMClient.embed` -> `build_embedding_store(db).upsert`
                     in ONE transaction; `doc_ref=str(article.id)`; update = idempotent replace;
                     backfill tool `backend/tools/backfill_kb_embedding.py`
  B E4 aggregate   : read-time aggregation (NO new table); `rca_service.aggregate/run`;
                     `RcaCandidate`/`RcaReport`; association cycle-safe, depth<=3 (>3 -> 422)
  C E5 playbook    : REUSE P3-4 workflow engine (`WORKFLOW_KINDS` includes 'playbook'); NO copy of
                     executor; run/approve/cancel reuse existing workflow primitives
  E5/E4 flags      : `ai.rca` / `ai.playbook` default False (perms unchanged == 16)
  scope token      : `GLOBAL_SCOPE_TOKEN="__public__"` (explicit wildcard, NOT NULL); always
                     included by `visible_entity_ids_for("kb", actor)`
  migration        : `P5_REV="f5a6b7c8d9e0"` parent `e9d8c7b6a5f4`; `workflow.kind` +
                     `ix_ops_event_entity_action_ts`; NO new table; C 7->8; chain 18->19
  API              : +3 URL keys => paths 164->167
                     1. GET  /api/v1/monitor/alerts/aggregate
                     2. POST /api/v1/monitor/alerts/{alert_id}/ai/rca
                     3. POST /api/v1/workflows/ai/suggest
  route order      : `aggregate` DECLARED BEFORE `get_alert` (`/alerts/{alert_id}`); fix (a), NOT a
                     converter. `/monitor/alerts/notanint` stays 422 (not 404).

EXPECTED: clean **RED** until the P5 backend lands (add-only). Import-guarded so a run reports
assertion failures, not collection errors. Offline only (no live PG/Redis; no migrations applied;
no network).

Run (backend checkout, backend venv):
    python -m pytest tests/test_p5_aiops_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import dataclasses
import importlib
import importlib.util
import inspect
import pathlib
import pkgutil
import re

import pytest

from tests.openapi_baseline import M6_P3_4_KEYS


def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_VERSIONS_DIR = _BACKEND / "alembic" / "versions"

_P4_HEAD = "e9d8c7b6a5f4"
_P5_REV = "f5a6b7c8d9e0"

P5_FLAGS = ("ai.rca", "ai.playbook")
P4_FLAGS = ("ai.enabled", "ai.events", "ai.ticket_assist", "ai.kb_assist")
P5_PATHS = {
    r"/api/v1/monitor/alerts/aggregate": {"get"},
    r"/api/v1/monitor/alerts/\{[^}]+\}/ai/rca": {"post"},
    r"/api/v1/workflows/ai/suggest": {"post"},
}


# ── seed / flags / perms ─────────────────────────────────────────────────────

def _seed():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P5 lock: app.db.seed unavailable: {seed}")
    return seed


def test_f1_p5_flags_default_false():
    """tuple: one flag per capability — `ai.rca` / `ai.playbook`, default False."""
    rules = getattr(_seed(), "DEFAULT_CONFIG_RULES", {})
    problems = []
    for flag in P5_FLAGS:
        entry = rules.get(flag)
        if entry is None:
            problems.append(f"{flag}: not seeded")
        elif entry.get("value") is not False:
            problems.append(f"{flag}: default must be False; got {entry.get('value')!r}")
    assert not problems, "P5 ai flags: " + "; ".join(problems)


def test_f1b_p4_flags_still_false():
    rules = getattr(_seed(), "DEFAULT_CONFIG_RULES", {})
    for flag in P4_FLAGS:
        assert rules.get(flag, {}).get("value") is False, f"{flag} must remain default False"


def test_p1_seed_menu_button_counts_unchanged():
    """tuple: E4/E5 hang off the existing `ai` menu => menus 27 / buttons 112 (add-only)."""
    tree = getattr(_seed(), "PERMISSION_TREE", [])
    menus = [node[0] for node in tree]
    buttons = [child[0] for node in tree for child in node[5]]
    assert len(menus) == 27, f"menus must stay 27; got {len(menus)}"
    assert len(buttons) == 112, f"buttons must stay 112; got {len(buttons)}"


# ── A1/A2: openapi surface ───────────────────────────────────────────────────

_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P5 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p5_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for pat, want in P5_PATHS.items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in _METHODS}
        miss = want - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P5 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_167():
    """Base M9 paths == 164; P5 adds 3 URL keys == 167. EXACT equality (not `>=`)."""
    paths = _openapi_paths()
    assert len(paths) == 167, (
        f"P5 paths must be exactly 167 (164 + 3 E4/E5 URL keys); got {len(paths)}. "
        "New keys: /monitor/alerts/aggregate, /monitor/alerts/{alert_id}/ai/rca, "
        "/workflows/ai/suggest."
    )
    removed = set(M6_P3_4_KEYS) - set(paths)
    assert not removed, f"openapi keys must not shrink below M6 baseline; removed={sorted(removed)}"


# ── G1/G2: migration graph + named rev symbol ────────────────────────────────

def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    return revs


def test_g1_migration_single_head_is_p5_rev():
    revs = _revision_graph()
    assert _P4_HEAD in revs, f"P4 head {_P4_HEAD} missing from versions dir"
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    head = heads[0]
    assert head == _P5_REV, f"P5 head must be the frozen rev `{_P5_REV}`; got {head}"
    assert revs[head] == _P4_HEAD, (
        f"P5 head must descend directly from P4 head {_P4_HEAD}; got parent {revs[head]!r}"
    )
    assert revs.get(_P4_HEAD) == "b2c3d4e5f6a8", "P4 head must still descend from P3-5 rev"


def test_g1b_workflow_kind_column_and_ops_event_index_present():
    """tuple: P5 migration content = `workflow.kind` + `ix_ops_event_entity_action_ts`; no new table."""
    tables = _tables()
    wf = tables.get("workflow")
    assert wf is not None, "workflow table missing"
    assert "kind" in set(wf.columns.keys()), "workflow.kind column must be added by P5"
    oe = tables.get("ops_event")
    assert oe is not None, "ops_event table missing"
    have = {ix.name for ix in oe.indexes}
    assert "ix_ops_event_entity_action_ts" in have, (
        f"ops_event must gain ix_ops_event_entity_action_ts; have {sorted(have)}"
    )
    forbidden = [t for t in tables if t in {"playbook", "playbook_step", "playbook_run"}]
    assert not forbidden, f"E5 must reuse the workflow engine; no new playbook table: {forbidden}"


def test_g2_p5_rev_is_named_symbol_in_C():
    """env lock must expose `P5_REV` (named symbol, not inline literal) and include it in C."""
    p = pathlib.Path(__file__).resolve().parent / "test_live_env_contract_lock.py"
    spec = importlib.util.spec_from_file_location("_p5_live_contract_lock", p)
    if spec is None or spec.loader is None:
        pytest.fail("P5 lock: cannot load test_live_env_contract_lock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert getattr(mod, "P5_REV", None) == _P5_REV, (
        f"test_live_env_contract_lock.py must expose named symbol P5_REV == {_P5_REV!r}"
    )
    assert _P5_REV in mod.MIGRATION_LIVE_FORBIDDEN, f"{_P5_REV} must be a member of C"
    assert mod.MIGRATION_LIVE_APPLICABLE & mod.MIGRATION_LIVE_FORBIDDEN == set(), (
        "B ∩ C must stay empty"
    )


# ── S1–S5: service symbols / layout ──────────────────────────────────────────

_DISCOVERY_CACHE: dict[str, tuple[str, object]] | None = None


def _discover() -> dict[str, tuple[str, object]]:
    global _DISCOVERY_CACHE
    if _DISCOVERY_CACHE is not None:
        return _DISCOVERY_CACHE
    found: dict[str, tuple[str, object]] = {}
    try:
        import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P5 lock: import app failed: {exc}")
    wanted = {
        "RcaCandidate", "RcaReport", "WORKFLOW_KINDS", "GLOBAL_SCOPE_TOKEN",
        "visible_entity_ids_for", "ScopeFilter", "EmbeddingStore",
        "build_embedding_store", "LLMClient",
    }
    for info in pkgutil.walk_packages(app.__path__, prefix="app."):
        try:
            m = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001
            continue
        for n in wanted:
            if n not in found and hasattr(m, n):
                found[n] = (info.name, getattr(m, n))
    _DISCOVERY_CACHE = found
    return found


def _discover_one(name: str):
    hit = _discover().get(name)
    return None if hit is None else hit[1]


def _require(name: str):
    obj = _discover_one(name)
    if obj is None:
        pytest.fail(f"P5 lock: symbol `{name}` not found in any app.* module (tuple v1->r2)")
    return obj


def test_s0_p5_module_layout():
    assert not isinstance(_try("app.services.rca_service"), Exception), (
        "app.services.rca_service must exist (E4)"
    )


def test_s1_rca_symbols():
    rca = _try("app.services.rca_service")
    if isinstance(rca, Exception):
        pytest.fail(f"P5 lock: app.services.rca_service unavailable: {rca}")
    for fn in ("aggregate", "run"):
        assert hasattr(rca, fn), f"rca_service must expose `{fn}` (E4)"
    _require("RcaCandidate")
    _require("RcaReport")


def test_s2_workflow_kinds_include_playbook():
    kinds = _require("WORKFLOW_KINDS")
    vals = set(kinds)
    assert {"workflow", "playbook"} <= vals, (
        f"WORKFLOW_KINDS must include both 'workflow' and 'playbook'; got {sorted(vals)}"
    )


def test_s3_global_scope_token():
    tok = _require("GLOBAL_SCOPE_TOKEN")
    assert tok == "__public__", f"GLOBAL_SCOPE_TOKEN must be '__public__'; got {tok!r}"


def _app_non_test_sources() -> list[tuple[pathlib.Path, str]]:
    app_dir = _BACKEND / "app"
    out: list[tuple[pathlib.Path, str]] = []
    for p in app_dir.rglob("*.py"):
        out.append((p, p.read_text(encoding="utf-8", errors="ignore")))
    return out


def test_s4_e3_ingestion_wiring_exists():
    """E3: a non-test app seam must call `embed(` + `upsert(` and carry `doc_ref` in one module.

    Excludes the store/gateway modules themselves (`embedding_store.py`/`llm_client.py`) so the
    assertion targets the *wiring* seam, not the primitives.
    """
    hits = []
    for p, txt in _app_non_test_sources():
        if p.name in {"embedding_store.py", "llm_client.py"}:
            continue
        if "upsert(" in txt and "embed(" in txt and "doc_ref" in txt:
            hits.append(str(p.relative_to(_BACKEND)))
    assert hits, (
        "E3 ingestion wiring missing: no app module calls embed(...) + build_embedding_store(...)"
        ".upsert(...) with doc_ref (tuple A / §29.1)"
    )
    tool = _BACKEND / "tools" / "backfill_kb_embedding.py"
    assert tool.exists(), "E3 backfill tool `backend/tools/backfill_kb_embedding.py` must exist"


def test_s5_e5_reuses_engine_no_executor_copy():
    """E5: reuse the P3-4 workflow engine; do NOT copy an executor / add a second run engine."""
    assert not isinstance(_try("app.services.workflow_service"), Exception), (
        "workflow_service must exist (reused by E5)"
    )
    wf = _try("app.services.workflow_service")
    assert hasattr(wf, "run_workflow"), "E5 must reuse workflow_service.run_workflow"
    dup = []
    for p, txt in _app_non_test_sources():
        if re.search(r"class\s+\w*Executor\b", txt):
            dup.append(str(p.relative_to(_BACKEND)))
    # Executors may exist for the base engine but E5 must not add a *playbook* executor.
    assert not any("playbook" in d.lower() for d in dup), (
        f"E5 must not add a playbook executor; found {dup}"
    )


# ── idempotent replace seam (E3) ─────────────────────────────────────────────

def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P5 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_b2_idempotent_replace_seam():
    """E3: re-ingesting the same article must replace, not duplicate.

    Accept either (a) a UNIQUE constraint on `kb_embedding(doc_ref, chunk_ref)`, or (b) a
    delete-then-insert seam in the ingestion wiring source.
    """
    kb = _tables().get("kb_embedding")
    unique_ok = False
    if kb is not None:
        for c in kb.constraints:
            cols = {col.name for col in getattr(c, "columns", [])}
            if {"doc_ref", "chunk_ref"} <= cols and type(c).__name__ == "UniqueConstraint":
                unique_ok = True
                break
    delete_ok = False
    for p, txt in _app_non_test_sources():
        if p.name in {"embedding_store.py"}:
            continue
        if "KbEmbedding" in txt and re.search(r"\.delete\(", txt) and "doc_ref" in txt:
            delete_ok = True
            break
    assert unique_ok or delete_ok, (
        "E3 idempotent replace missing: need UNIQUE(kb_embedding.doc_ref, chunk_ref) "
        "or a delete-by-doc_ref seam before upsert"
    )


# ── US-03 scope double proof (public token + not-retrieved) ───────────────────

class _ScopeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _ScopeSession:
    """Minimal session stub: every `execute(...).all()` returns the canned rows."""

    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []
        self.statements: list = []

    def execute(self, stmt, *a, **k):
        self.statements.append(stmt)
        return _ScopeResult(self._rows)


class _Actor:
    def __init__(self, *, is_admin: bool, uid: int = 1):
        self.is_admin = is_admin
        self.id = uid
        self.visible_group_ids = []


def test_b1_public_token_always_in_kb_scope():
    """tuple: `visible_entity_ids_for("kb", actor)` ALWAYS includes `__public__` (explicit wildcard)."""
    fn = _require("visible_entity_ids_for")
    tok = _require("GLOBAL_SCOPE_TOKEN")
    for admin in (False, True):
        db = _ScopeSession(rows=[(1,)])
        ids = fn("kb", _Actor(is_admin=admin), db)
        assert tok in set(ids), (
            f"kb scope must always include {tok!r} (actor admin={admin}); got {sorted(ids)}"
        )


# ── R0–R2: HTTP-level route order (fix (a); the false-green guard) ────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


def _mk_tables():
    import app.db.models  # noqa: F401,PLC0415
    from app.db.base import Base  # noqa: PLC0415

    tl = Base.metadata.tables
    names = (
        "config_rule", "sys_audit_log", "sys_user",
        "ops_event", "kb_embedding", "ai_action", "ai_eval_case", "ai_eval_run",
        "mon_alert", "workflow", "workflow_version", "workflow_run", "workflow_node_run",
    )
    return [tl[n] for n in names if n in tl]


@pytest.fixture()
def p5_client(tmp_path):
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p5.db'}", future=True)
    Base.metadata.create_all(engine, tables=_mk_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()
    prev_bind = getattr(_dbs.SessionLocal, "kw", {}).get("bind")
    _dbs.SessionLocal.configure(bind=engine)

    import app.main as main  # noqa: PLC0415
    from app.api.deps import CurrentUser, get_current_user  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    main.app.dependency_overrides[get_db] = lambda: (yield session)

    def set_admin():
        user = CurrentUser(
            user_id=1, username="qa", is_admin=True,
            permissions=["ai:use", "ai:admin"], visible_group_ids=[],
        )
        main.app.dependency_overrides[get_current_user] = lambda: user
        return user

    def set_flag(key: str, on: bool):
        from app.db.models.notify import ConfigRule  # noqa: PLC0415

        row = session.query(ConfigRule).filter_by(rule_key=key).one_or_none()
        if row is None:
            session.add(ConfigRule(rule_key=key, rule_value={"value": on}))
        else:
            row.rule_value = {"value": on}
        session.commit()

    try:
        yield TestClient(main.app), set_admin, set_flag
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_r0_aggregate_reachable_not_422(p5_client):
    """Route order (a): `aggregate` must resolve to its own route (200), NOT `{alert_id}` (422).

    Only a direct `rca_service.aggregate(...)` unit call would be false-green here.
    """
    client, set_admin, set_flag = p5_client
    set_flag("ai.enabled", True)
    set_flag("ai.rca", True)
    set_admin()
    r = client.get("/api/v1/monitor/alerts/aggregate")
    assert r.status_code != 422, (
        "`/monitor/alerts/aggregate` hit the `{alert_id}` route (422) — declare `aggregate` "
        f"BEFORE `get_alert` (fix (a)); got {r.status_code} {r.text}"
    )
    assert r.status_code == 200, (
        f"aggregate must return 200 aggregate body; got {r.status_code} {r.text}"
    )


def test_r1_static_aggregate_before_alert_id():
    """Static guard: the aggregate route is registered before `/alerts/{alert_id}`."""
    mod = _try("app.api.v1.endpoints.monitor")
    if isinstance(mod, Exception):
        pytest.fail(f"P5 lock: monitor endpoint unavailable: {mod}")
    paths = [getattr(rt, "path", "") for rt in mod.router.routes]
    agg = [i for i, p in enumerate(paths) if p.endswith("/alerts/aggregate")]
    idr = [i for i, p in enumerate(paths) if p.endswith("/alerts/{alert_id}")]
    assert agg, f"aggregate route missing (routes={paths})"
    assert idr, f"/alerts/{{alert_id}} route missing (routes={paths})"
    assert min(agg) < min(idr), (
        f"aggregate (idx {min(agg)}) must be declared BEFORE /alerts/{{alert_id}} "
        f"(idx {min(idr)}) so it is not swallowed"
    )


def test_r2_notanint_stays_422(p5_client):
    """fix (a) keeps the `{alert_id}` semantics: `/alerts/notanint` => 422 (NOT 404)."""
    client, set_admin, _ = p5_client
    set_admin()
    r = client.get("/api/v1/monitor/alerts/notanint")
    assert r.status_code == 422, (
        f"fix (a) keeps int path semantics: notanint must be 422 (not 404); got "
        f"{r.status_code} {r.text}"
    )


# ── E4 depth (tuple r2.1, @架构 seq3337 / @代码reviewer 3336) ──────────────────

def test_g3_e4_reuses_cmdb_topology_single_source():
    """r2.1 item 3: E4 association traversal must REUSE `cmdb_service` topology read
    (`_clamp_depth` + layered traversal), not start a second BFS."""
    rca = _try("app.services.rca_service")
    if isinstance(rca, Exception):
        pytest.fail(f"P5 lock: app.services.rca_service unavailable: {rca}")
    src = inspect.getsource(rca)
    assert "cmdb_service" in src, (
        "E4 association traversal must reuse `cmdb_service` (r2.1 item 3: no second BFS)"
    )


def test_b3_depth_domain_and_default():
    """r2.1 item 1: legal domain `0..3`, default 2, `0` legal, `<0`|`>3` raise."""
    cmdb = _try("app.services.cmdb_service")
    if isinstance(cmdb, Exception):
        pytest.fail(f"P5 lock: app.services.cmdb_service unavailable: {cmdb}")
    assert cmdb._clamp_depth(None) == 2, "default depth must be 2 (P3-3 same value)"
    assert cmdb._clamp_depth(0) == 0, "depth 0 must be legal (no `ge=1` drift)"
    assert cmdb._clamp_depth(3) == 3, "depth 3 must be legal (upper bound)"
    for bad in (-1, 4):
        with pytest.raises(cmdb.ValidationError):
            cmdb._clamp_depth(bad)


def test_b4_depth_execution_limits_layers(monkeypatch):
    """r2.1 item 2: depth must be EXECUTED (layered traversal), not merely validated.

    A chain of length >=4 proves `depth=1/2/3` grows monotonically and never includes the
    `depth+1` layer — defeats a "accept depth but always full-BFS" false-green.
    """
    cmdb = _try("app.services.cmdb_service")
    if isinstance(cmdb, Exception):
        pytest.fail(f"P5 lock: app.services.cmdb_service unavailable: {cmdb}")

    class _Edge:
        src_type, src_id, dst_type, dst_id, rel_type = "host", 0, "host", 0, "depends"

    def _edge(a: int, b: int) -> _Edge:
        e = _Edge()
        e.src_type, e.src_id, e.dst_type, e.dst_id = "host", a, "host", b
        return e

    chain = {
        ("host", 1): [_edge(1, 2)],
        ("host", 2): [_edge(2, 3)],
        ("host", 3): [_edge(3, 4)],
        ("host", 4): [_edge(4, 5)],
        ("host", 5): [],
    }
    monkeypatch.setattr(cmdb, "_require_feature", lambda db: None)
    monkeypatch.setattr(cmdb, "_visible_scope", lambda db, user: None)
    monkeypatch.setattr(cmdb, "_entity_visible", lambda scope, t, i: True)
    monkeypatch.setattr(cmdb, "_labels", lambda db, keys: {})
    monkeypatch.setattr(
        cmdb, "_edges_for", lambda db, node, direction, rel_types: chain.get(node, [])
    )

    class _User:
        def require_perm(self, *_a, **_k):  # noqa: ANN002,ANN003
            return None

    class _DB:
        pass

    def _ids(depth):
        out = cmdb.impact(_DB(), _User(), "host", 1, "down", depth, None)
        return {n["id"] for n in out["affected"]}

    d1, d2, d3 = _ids(1), _ids(2), _ids(3)
    assert d1 == {2}, f"depth=1 must reach only layer 1; got {d1}"
    assert d2 == {2, 3}, f"depth=2 must reach layers 1..2; got {d2}"
    assert d3 == {2, 3, 4}, f"depth=3 must reach layers 1..3; got {d3}"
    assert 5 not in d3, "depth=3 must NOT include the depth+1 (layer 4) member"
    assert d1 <= d2 <= d3, f"candidate set must grow monotonically with depth; {d1} {d2} {d3}"
