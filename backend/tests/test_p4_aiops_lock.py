r"""P4（AIOps）contract locks — @单元 lock-first, add-only.

Frozen contract: @架构 **P4 tuple v1** (seq3203) + 勘误#1 (seq3207: `P4_REV`).
Base = release **M8 `24e80931`** (master).

Pinned surface (seq3203/seq3207):
  E1 events        : table `ops_event(id,ts,entity_type,entity_id,action,result,
                     source,refs,trace_id,created_at)`; source∈{monitor,exec,audit,
                     ticket,kb}; 3 indexes; single write seam `event_service.emit`;
                     forward-only; envelope {list,total,page,size}
  E2 ticket assist : /tickets/{id}/ai/suggest ; /tickets/{id}/ai/similar
  E3 kb RAG        : table `kb_embedding(id,doc_ref,chunk_ref,embedding,entity_scope,
                     dim,created_at)`; /kb/search/semantic ; /kb/ai/answer
  E7 governance    : table `ai_action(...decision∈{adopted,rejected,auto})`;
                     `ai_action`/`ops_event` append-only; flags `ai.*` default False
  E8 eval          : `ai_eval_case`/`ai_eval_run`; `eval_service.run(cases)->EvalReport`
  ADR#1 gateway    : `LLMClient.complete(messages,*,purpose)` / `.embed(texts)`;
                     stub `EchoLLMClient`
  ADR#2 storage(b) : same PG, application-side cosine, NO pgvector extension;
                     `EmbeddingStore.upsert/query`, `_candidates(*,query_vector,scope,limit)`;
                     impls `PostgresArrayEmbeddingStore` / `InMemoryEmbeddingStore`
  ADR#3 US-03      : `scope` is a QUERY input (never post-filter); `ScopeFilter`
                     carries `entity_type`; dispatcher `visible_entity_ids_for`;
                     unknown entity_type => fail-closed
  migration        : `P4_REV="e9d8c7b6a5f4"` parent `b2c3d4e5f6a8`; C 6->7; chain 17->18
  perms            : shared `ai:use`/`ai:admin` (14->16 named codes)
  API              : +8 URL keys => paths 156->164

EXPECTED: clean **RED** until the P4 backend lands (add-only). Import-guarded so a
run reports assertion failures, not collection errors. Offline only (no live PG/Redis;
no migrations applied; no network).

Run (backend checkout, backend venv):
    python -m pytest tests/test_p4_aiops_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import dataclasses
import importlib
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


# ── P1: permission codes (seed PERMISSION_TREE) ──────────────────────────────

P4_PERMS = {"ai:use", "ai:admin"}
# P3-6 operation-level set (provider 5 + release 9 == 14). P4 adds the shared
# `ai:use`/`ai:admin` (NOT per-capability) => 14 + 2 == 16 named endpoint codes.
_P36_OP_CODES = {
    "cicd:provider:list", "cicd:provider:add", "cicd:provider:edit",
    "cicd:provider:del", "cicd:provider:test",
    "release:list", "release:add", "release:view", "release:canary",
    "release:promote", "release:rollback", "release:cancel",
    "release:deploy", "release:fail",
}


def _perm_codes() -> set[str]:
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P4 lock: app.db.seed unavailable: {seed}")
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_ai_permission_codes_registered():
    codes = _perm_codes()
    missing = P4_PERMS - codes
    assert not missing, f"P4 permission codes missing from PERMISSION_TREE: {sorted(missing)}"


def test_p1b_p4_permission_total_16():
    """tuple F: shared `ai:use`/`ai:admin` (14 -> 16 named endpoint codes).

    @架构 seq3220 ②: assert the seeded endpoint-code universe is exactly 16.
    """
    assert _P36_OP_CODES | P4_PERMS == _P36_OP_CODES | {"ai:use", "ai:admin"}
    assert len(_P36_OP_CODES | P4_PERMS) == 16, "14 (P3-6) + 2 (ai:use/ai:admin) == 16"
    codes = _perm_codes()
    assert P4_PERMS <= codes, f"ai perms not seeded: {sorted(P4_PERMS - codes)}"
    seeded_endpoint_codes = (_P36_OP_CODES | P4_PERMS) & codes
    assert len(seeded_endpoint_codes) == 16, (
        f"seeded endpoint-code set must be exactly 16; got {len(seeded_endpoint_codes)}: "
        f"{sorted(seeded_endpoint_codes)}"
    )


def test_p1c_seed_menu_button_counts():
    """tuple seq3212 #1: new top menu `ai` + 2 buttons => menus 26->27, buttons 110->112."""
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P4 lock: app.db.seed unavailable: {seed}")
    tree = getattr(seed, "PERMISSION_TREE", [])
    menus = [node[0] for node in tree]
    buttons = [child[0] for node in tree for child in node[5]]
    assert len(menus) == 27, f"menus must be 27 (26 + `ai`); got {len(menus)}"
    assert len(buttons) == 112, f"buttons must be 112 (110 + ai:use/ai:admin); got {len(buttons)}"


def test_p1d_ai_perms_admin_only():
    """tuple seq3212 #1: only `admin` binds ai perms (operator/viewer unchanged)."""
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P4 lock: app.db.seed unavailable: {seed}")
    roles = getattr(seed, "DEFAULT_ROLES", {})
    assert P4_PERMS <= set(roles.get("admin", {}).get("permissions", [])), (
        "admin must bind {ai:use, ai:admin}"
    )
    for r in ("operator", "viewer"):
        bound = set(roles.get(r, {}).get("permissions", []))
        assert not (P4_PERMS & bound), f"{r} must NOT bind ai perms; got {sorted(P4_PERMS & bound)}"


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

_EVENTS = r"/api/v1/events"
_AI = r"/api/v1/ai"


def _p4_paths() -> dict[str, set[str]]:
    return {
        _EVENTS: {"get"},
        _EVENTS + r"/\{[^}]+\}": {"get"},
        r"/api/v1/tickets/\{[^}]+\}/ai/suggest": {"post"},
        r"/api/v1/tickets/\{[^}]+\}/ai/similar": {"get"},
        r"/api/v1/kb/search/semantic": {"post"},
        r"/api/v1/kb/ai/answer": {"post"},
        _AI + r"/feedback": {"post"},
        _AI + r"/actions": {"get"},
    }


_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p4_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for pat, want in _p4_paths().items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in _METHODS}
        miss = want - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P4 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_164():
    """Base M8 paths == 156; P4 adds 8 URL keys == 164. EXACT equality (not `>=`)."""
    paths = _openapi_paths()
    assert len(paths) == 164, (
        f"P4 paths must be exactly 164 (156 + 8 AIOps URL keys); got {len(paths)}. "
        "OpenAPI `paths` is URL-keyed: /events, /events/{id}, /tickets/{id}/ai/suggest, "
        "/tickets/{id}/ai/similar, /kb/search/semantic, /kb/ai/answer, /ai/feedback, /ai/actions."
    )
    removed = set(M6_P3_4_KEYS) - set(paths)
    assert not removed, (
        f"openapi keys must not shrink below the M6 baseline (layer ④): removed={sorted(removed)}"
    )


# ── M1–M4: SQLAlchemy tables / columns / indexes ─────────────────────────────

P4_TABLES = ("ops_event", "kb_embedding", "ai_action", "ai_eval_case", "ai_eval_run")
OPS_EVENT_COLS = {
    "id", "ts", "entity_type", "entity_id", "action", "result", "source",
    "refs", "trace_id", "created_at",
}
KB_EMBEDDING_COLS = {"id", "doc_ref", "chunk_ref", "embedding", "entity_scope", "dim", "created_at"}
AI_ACTION_COLS = {
    "id", "model_name", "model_version", "input_snapshot", "confidence",
    "basis_refs", "trace_id", "actor", "decision", "created_at",
}
OPS_EVENT_INDEXES = {"ix_ops_event_source_ts", "ix_ops_event_entity_ts", "ix_ops_event_refs_gin"}
AI_ACTION_DECISIONS = {"adopted", "rejected", "auto"}
OPS_EVENT_SOURCES = {"monitor", "exec", "audit", "ticket", "kb"}
# E8 (a)-min columns (@架构 seq3230 / @需求 seq3231).
AI_EVAL_CASE_COLS = {"id", "name", "input", "expected", "is_neg_control", "created_at"}
AI_EVAL_RUN_COLS = {
    "id", "case_id", "model_name", "model_version", "actual", "passed", "report", "created_at",
}


def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_p4_tables_registered():
    tables = _tables()
    missing = [t for t in P4_TABLES if t not in tables]
    assert not missing, f"P4 must define {list(P4_TABLES)}; missing {missing}"


def test_m2_p4_core_columns():
    tables = _tables()
    problems = []
    for name, want in (
        ("ops_event", OPS_EVENT_COLS),
        ("kb_embedding", KB_EMBEDDING_COLS),
        ("ai_action", AI_ACTION_COLS),
    ):
        t = tables.get(name)
        if t is None:
            problems.append(f"{name}: table missing")
            continue
        miss = want - set(t.columns.keys())
        if miss:
            problems.append(f"{name}: missing columns {sorted(miss)}")
    assert not problems, "P4 column contract: " + "; ".join(problems)


def test_m2b_eval_tables_core_columns():
    """@架构 seq3230 / @需求 seq3231: pinned eval column sets (E8 (a)-min)."""
    tables = _tables()
    problems = []
    for name, want in (("ai_eval_case", AI_EVAL_CASE_COLS), ("ai_eval_run", AI_EVAL_RUN_COLS)):
        t = tables.get(name)
        if t is None:
            problems.append(f"{name}: table missing")
            continue
        miss = want - set(t.columns.keys())
        if miss:
            problems.append(f"{name}: missing columns {sorted(miss)}")
    assert not problems, "P4 eval-table contract: " + "; ".join(problems)

    case = tables.get("ai_eval_case")
    if case is not None and "is_neg_control" in case.columns:
        from sqlalchemy import Boolean  # noqa: PLC0415

        ctype = case.columns["is_neg_control"].type
        assert isinstance(ctype, Boolean), (
            "ai_eval_case.is_neg_control must be Boolean (@架构 seq3248 ⑧; frozen as "
            f"`bool`); got {ctype!r}"
        )


def test_m3_ops_event_indexes():
    t = _tables().get("ops_event")
    if t is None:
        pytest.fail("P4 lock: table `ops_event` missing")
    have = {ix.name for ix in t.indexes}
    miss = OPS_EVENT_INDEXES - have
    assert not miss, f"ops_event missing indexes {sorted(miss)} (have {sorted(have)})"


def test_m4_ai_action_decision_enum():
    """`decision` vocabulary must be exactly {adopted,rejected,auto} (tuple D)."""
    found = _discover_one("AI_ACTION_DECISIONS") or _discover_one("AI_DECISIONS")
    decision_col = _col_enum_values("ai_action", "decision")
    if found is not None:
        vals = set(found)
    elif decision_col is not None:
        vals = set(decision_col)
    else:
        pytest.fail(
            "P4 lock: ai_action decision vocabulary not expressible — expected a module "
            "constant (AI_ACTION_DECISIONS) or a CHECK/Enum on `ai_action.decision`"
        )
    assert vals == AI_ACTION_DECISIONS, f"decision enum must be {sorted(AI_ACTION_DECISIONS)}; got {sorted(vals)}"


def _col_enum_values(table: str, col: str) -> set[str] | None:
    t = _tables().get(table)
    if t is None or col not in t.columns:
        return None
    c = t.columns[col]
    vals = getattr(getattr(c, "type", None), "enums", None)
    return set(vals) if vals else None


# ── R1: §12.5 same-table reuse (no second relation table) ────────────────────

def test_r1_no_second_relation_table():
    tables = _tables()
    assert "entity_relation" in tables, "P4 must reuse `entity_relation` (§12.5)"
    forbidden = [t for t in tables if t in {"cmdb_ci_relation", "ci_relation", "topology_edge"}]
    assert not forbidden, (
        f"§12.5: AIOps must NOT create a second relation table; found {forbidden}"
    )


# ── F1: ai feature flags default off ─────────────────────────────────────────

AI_FLAGS = ("ai.enabled", "ai.events", "ai.ticket_assist", "ai.kb_assist")


def test_f1_ai_flags_default_false():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P4 lock: app.db.seed unavailable: {seed}")
    rules = getattr(seed, "DEFAULT_CONFIG_RULES", {})
    problems = []
    for flag in AI_FLAGS:
        entry = rules.get(flag)
        if entry is None:
            problems.append(f"{flag}: not seeded")
        elif entry.get("value") is not False:
            problems.append(f"{flag}: default must be False; got {entry.get('value')!r}")
    assert not problems, "P4 ai flags: " + "; ".join(problems)


# ── G1/G2: migration single head descending from P3-5 rev ────────────────────

_VERSIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
_P35_HEAD = "b2c3d4e5f6a8"
_P4_REV = "e9d8c7b6a5f4"


def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    return revs


def test_g1_migration_single_head_descends_from_p35():
    revs = _revision_graph()
    assert _P35_HEAD in revs, f"P3-5 head {_P35_HEAD} missing from versions dir"
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    head = heads[0]
    assert head == _P4_REV, f"P4 head must be the frozen rev `{_P4_REV}`; got {head}"
    assert revs[head] == _P35_HEAD, (
        f"P4 head must descend directly from P3-5 rev {_P35_HEAD}; got parent {revs[head]!r}"
    )


def test_g2_p4_rev_is_named_symbol_in_C():
    """env lock must expose `P4_REV` (named symbol, not inline) and include it in C."""
    import importlib.util  # noqa: PLC0415

    p = pathlib.Path(__file__).resolve().parent / "test_live_env_contract_lock.py"
    spec = importlib.util.spec_from_file_location("_p4_live_contract_lock", p)
    if spec is None or spec.loader is None:
        pytest.fail("P4 lock: cannot load test_live_env_contract_lock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert getattr(mod, "P4_REV", None) == _P4_REV, (
        f"test_live_env_contract_lock.py must expose named symbol P4_REV == {_P4_REV!r}"
    )
    assert _P4_REV in mod.MIGRATION_LIVE_FORBIDDEN, f"{_P4_REV} must be a member of C"
    assert mod.MIGRATION_LIVE_APPLICABLE & mod.MIGRATION_LIVE_FORBIDDEN == set(), (
        "B ∩ C must stay empty"
    )


# ── S1–S7: service interfaces (name discovery; module paths pending @架构 pin) ─

_DISCOVERY_CACHE: dict[str, tuple[str, object]] | None = None


def _discover() -> dict[str, tuple[str, object]]:
    global _DISCOVERY_CACHE
    if _DISCOVERY_CACHE is not None:
        return _DISCOVERY_CACHE
    found: dict[str, tuple[str, object]] = {}
    try:
        import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: import app failed: {exc}")
    wanted = {
        "LLMClient", "EchoLLMClient", "LLMResult",
        "EmbeddingStore", "ScopeFilter", "EmbeddingHit",
        "PostgresArrayEmbeddingStore", "InMemoryEmbeddingStore",
        "visible_entity_ids_for", "EvalReport",
        "AI_ACTION_DECISIONS", "AI_DECISIONS", "OPS_EVENT_SOURCES",
        "EmbeddingRecord", "EmbeddingUpsert", "EmbeddingDoc", "UpsertRecord",
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
        pytest.fail(f"P4 lock: symbol `{name}` not found in any app.* module (tuple v1)")
    return obj


_PINNED_MODULES = (
    "app.services.llm_client",
    "app.services.embedding_store",
    "app.services.ai_scope",
    "app.services.event_service",
    "app.services.eval_service",
    "app.db.models.ops_event",
    "app.db.models.ai",
    "app.api.v1.endpoints.ops_event",
    "app.api.v1.endpoints.ai",
)


def test_s0_pinned_module_layout():
    """seq3212 #4: canonical module layout for the P4 service/surface symbols."""
    missing = [m for m in _PINNED_MODULES if isinstance(_try(m), Exception)]
    assert not missing, f"P4 pinned module layout incomplete (seq3212 #4): missing {missing}"


def test_s1_llm_client_symbols():
    cls = _require("LLMClient")
    _require("EchoLLMClient")
    res = _require("LLMResult")
    for meth in ("complete", "embed"):
        assert hasattr(cls, meth), f"LLMClient must expose `{meth}` (ADR#1)"
    if dataclasses.is_dataclass(res):
        fields = {f.name for f in dataclasses.fields(res)}
    else:
        fields = set(getattr(res, "__annotations__", {}) or {})
    assert {"text", "model_name", "model_version", "usage", "raw"} <= fields, (
        f"LLMResult fields must include text/model_name/model_version/usage/raw; got {sorted(fields)}"
    )


def test_s2_embedding_store_symbols():
    base = _require("EmbeddingStore")
    _require("PostgresArrayEmbeddingStore")
    _require("InMemoryEmbeddingStore")
    for meth in ("upsert", "query", "_candidates"):
        assert hasattr(base, meth), f"EmbeddingStore must expose `{meth}` (ADR#2/#3)"


def test_s3_scope_carries_entity_type_and_query_takes_scope():
    sf = _require("ScopeFilter")
    if dataclasses.is_dataclass(sf):
        names = {f.name for f in dataclasses.fields(sf)}
    else:
        names = set(getattr(sf, "__annotations__", {}) or {})
    assert {"entity_type", "entity_ids"} <= names, (
        f"ScopeFilter must carry entity_type + entity_ids (ADR#3); fields={sorted(names)}"
    )
    q = _require("EmbeddingStore").query
    params = set(inspect.signature(q).parameters)
    assert "scope" in params, (
        f"EmbeddingStore.query must take `scope` as a QUERY input (ADR#3); params={sorted(params)}"
    )
    c = _require("EmbeddingStore")._candidates
    cparams = set(inspect.signature(c).parameters)
    assert "scope" in cparams, (
        f"EmbeddingStore._candidates must take `scope` (ADR#3 spy seam); params={sorted(cparams)}"
    )


def test_s8_event_emit_signature():
    """seq3212 #5: emit(db,*,entity_type,entity_id,action,result,source,refs,trace_id)."""
    mods = _event_service_modules()
    assert mods, "P4 must provide `app.services.event_service`"
    emit = next((getattr(m, "emit") for m in mods if hasattr(m, "emit")), None)
    if emit is None:
        pytest.fail("event_service.emit missing (single write seam)")
    params = set(inspect.signature(emit).parameters)
    want = {"entity_type", "entity_id", "action", "result", "source"}
    miss = want - params
    assert not miss, f"emit must accept {sorted(want)}; missing {sorted(miss)} params={sorted(params)}"
    src = _discover_one("OPS_EVENT_SOURCES")
    if src is not None:
        assert set(src) == OPS_EVENT_SOURCES, (
            f"OPS_EVENT_SOURCES must be {sorted(OPS_EVENT_SOURCES)}; got {sorted(src)}"
        )


def test_s4_visible_entity_ids_for_dispatcher():
    fn = _require("visible_entity_ids_for")
    params = list(inspect.signature(fn).parameters)
    assert len(params) >= 2, (
        f"visible_entity_ids_for must take (entity_type, actor); params={params}"
    )


def test_s5_event_service_emit_single_seam():
    # `emit` is generic; require a module named event_service to carry it.
    mods = _event_service_modules()
    assert mods, "P4 must provide `app.services.event_service` (single write seam)"
    emits = [m for m in mods if hasattr(m, "emit")]
    assert emits, "event_service must expose `emit(db, ...)` (single write seam)"
    assert _no_bypass_ops_event_insert(), (
        "ops_event INSERT must live solely in event_service (static grep; no bypass)"
    )


def _event_service_modules() -> list:
    out = []
    try:
        import app.services  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: import app.services failed: {exc}")
    for info in pkgutil.iter_modules(app.services.__path__, prefix="app.services."):
        if info.name.rsplit(".", 1)[-1] != "event_service":
            continue
        try:
            out.append(importlib.import_module(info.name))
        except Exception:  # noqa: BLE001
            continue
    return out


def _no_bypass_ops_event_insert() -> bool:
    """Grep root `app/` for `OpsEvent(` construction outside the write-seam whitelist.

    Frozen judge scope (⑦, @架构 seq3240/seq3242): root `app/` + regex
    `\\bOpsEvent\\s*\\(` + whitelist {`app/services/event_service.py`,
    `app/db/models/ops_event.py`}. Scanning only `app/services` would假绿 a bypass
    from `app/api/*` (e.g. `endpoints/ops_event.py`).
    """
    try:
        import app  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    root = pathlib.Path(app.__file__).resolve().parent
    whitelist = {
        (root / "services" / "event_service.py").resolve(),
        (root / "db" / "models" / "ops_event.py").resolve(),
    }
    for py in root.rglob("*.py"):
        if py.resolve() in whitelist:
            continue
        try:
            txt = py.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if re.search(r"\bOpsEvent\s*\(", txt):
            return False
    return True


def test_s6_eval_service_run_symbol():
    _require("EvalReport")
    mods = _modules_named("eval_service")
    assert mods, "P4 must provide `app.services.eval_service` (E8)"
    assert any(hasattr(m, "run") for m in mods), "eval_service must expose `run(cases)`"


def _modules_named(name: str) -> list:
    out = []
    try:
        import app.services  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return out
    for info in pkgutil.iter_modules(app.services.__path__, prefix="app.services."):
        if info.name.rsplit(".", 1)[-1] != name:
            continue
        try:
            out.append(importlib.import_module(info.name))
        except Exception:  # noqa: BLE001
            continue
    return out


def test_s7_no_pgvector_dependency():
    """ADR#2 (b): same-PG application-side vectors — NO pgvector extension/dep."""
    pyproject = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    txt = pyproject.read_text(encoding="utf-8")
    assert "pgvector" not in txt.lower(), "ADR#2 (b) forbids a pgvector dependency"


# ── B1: US-03 behavioural lock (offline) ─────────────────────────────────────

def test_b1_embedding_store_query_scopes_candidates():
    """ADR#3: the candidate fetch must receive `scope`; an out-of-scope record that
    physically exists must never be returned (guards retrieve-then-filter)."""
    base = _require("EmbeddingStore")
    inmem = _require("InMemoryEmbeddingStore")
    scope_cls = _require("ScopeFilter")
    seen: list = []
    orig = getattr(inmem, "_candidates", None)
    if orig is None:
        pytest.fail("InMemoryEmbeddingStore must define `_candidates` (ADR#3)")
    store = inmem()

    def spy(*args, **kwargs):
        seen.append(kwargs.get("scope", args[0] if args else None))
        return orig(store, *args, **kwargs)

    try:
        inmem._candidates = lambda self, *a, **kw: spy(*a, **kw)
        try:
            scope = _make_scope(scope_cls, entity_type="host", ids=[7])
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"P4 lock: cannot build ScopeFilter for the US-03 probe: {exc}")
        try:
            store.query([0.0, 0.0, 0.0], scope=scope, limit=5)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"P4 lock: query() raised before scope could be asserted: {exc}")
        assert seen, "EmbeddingStore._candidates was never invoked by query()"
        assert any(s is not None for s in seen), (
            "query() must forward `scope` to _candidates (ADR#3: no post-filter)"
        )
    finally:
        if orig is not None:
            inmem._candidates = orig


def _make_scope(scope_cls, *, entity_type: str, ids: list[int]):
    """Best-effort construction of a ScopeFilter across plausible shapes."""
    if dataclasses.is_dataclass(scope_cls):
        names = {f.name for f in dataclasses.fields(scope_cls)}
        kw = {}
        if "entity_type" in names:
            kw["entity_type"] = entity_type
        for cand in ("ids", "visible_entity_ids", "entity_ids", "scope_ids"):
            if cand in names:
                kw[cand] = list(ids)
                break
        return scope_cls(**kw)
    try:
        return scope_cls(entity_type=entity_type, ids=ids)
    except TypeError:
        return scope_cls(entity_type, ids)


# ── R0–R2: runtime gate order (offline TestClient) ───────────────────────────

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
    import app.db.models  # noqa: F401,PLC0415 (register all models)
    from app.db.base import Base  # noqa: PLC0415

    tl = Base.metadata.tables
    names = (
        "config_rule", "sys_audit_log", "sys_user",
        "ops_event", "kb_embedding", "ai_action", "ai_eval_case", "ai_eval_run",
    )
    return [tl[n] for n in names if n in tl]


@pytest.fixture()
def ai_client(tmp_path):
    """Yields ``(client, set_user, set_flag)`` for the AIOps gate-order locks."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p4.db'}", future=True)
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

    def set_user(perms, admin=False):
        user = CurrentUser(
            user_id=1, username="qa", is_admin=admin,
            permissions=list(perms), visible_group_ids=[],
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
        yield TestClient(main.app), set_user, set_flag
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_r0_events_feature_gate_first_400(ai_client):
    """tuple seq3212 #2: feature gate FIRST — flag off => 400 for ANY caller (even admin)."""
    client, set_user, set_flag = ai_client
    set_flag("ai.events", False)
    set_user([], admin=True)
    r = client.get("/api/v1/events")
    assert r.status_code == 400, (
        f"feature-first: ai.events off => 400 for any caller; got {r.status_code} {r.text}"
    )


def test_r1_events_missing_perm_403(ai_client):
    """tuple seq3212 #2/#3: flag on + missing `ai:use` => 403."""
    client, set_user, set_flag = ai_client
    set_flag("ai.enabled", True)
    set_flag("ai.events", True)
    set_user([])  # authenticated but no ai:use
    r = client.get("/api/v1/events")
    assert r.status_code == 403, (
        f"flag on + missing ai:use => 403; got {r.status_code} {r.text}"
    )


def test_r2_ai_actions_admin_only_403(ai_client):
    """tuple seq3212 #3: `GET /ai/actions` requires `ai:admin` (not merely ai:use)."""
    client, set_user, set_flag = ai_client
    set_flag("ai.enabled", True)
    set_user(["ai:use"])  # ai:use alone is insufficient
    r = client.get("/api/v1/ai/actions")
    assert r.status_code == 403, (
        f"/ai/actions requires ai:admin; got {r.status_code} {r.text}"
    )


# ── B2: US-03 behavioural NEGATIVE (retrieve-then-filter must be impossible) ──

def _make_record(**kw):
    for cls_name in ("EmbeddingRecord", "EmbeddingUpsert", "EmbeddingDoc", "UpsertRecord"):
        cls = _discover_one(cls_name)
        if cls is not None:
            try:
                return cls(**kw)
            except TypeError:
                continue
    return dict(kw)


def _hit_refs(hits) -> set:
    out = set()
    for h in hits:
        if isinstance(h, dict):
            out.add((h.get("doc_ref"), h.get("chunk_ref")))
        else:
            out.add((getattr(h, "doc_ref", None), getattr(h, "chunk_ref", None)))
    return out


def test_b2_candidates_excludes_out_of_scope_records():
    """ADR#3 (@架构 seq3216): an out-of-scope record that PHYSICALLY exists must
    never be returned by `_candidates`/`query` — direct proof of "query-time
    filtering", not retrieve-then-filter.

    Negative control for B1 (which only proves `scope` is forwarded): a store that
    accepts `scope` but ignores it (return-all + post-filter) MUST fail HERE.
    """
    inmem = _require("InMemoryEmbeddingStore")
    scope_cls = _require("ScopeFilter")
    store = inmem()
    in_rec = _make_record(
        doc_ref="in", chunk_ref="in#0", embedding=[1.0, 0.0, 0.0], entity_scope=7, dim=3,
    )
    out_rec = _make_record(
        doc_ref="out", chunk_ref="out#0", embedding=[0.0, 1.0, 0.0], entity_scope=9, dim=3,
    )
    try:
        store.upsert([in_rec, out_rec])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: InMemoryEmbeddingStore.upsert failed: {exc}")

    scope = _make_scope(scope_cls, entity_type="host", ids=[7])
    qv = [1.0, 0.0, 0.0]

    try:
        cand = store._candidates(query_vector=qv, scope=scope, limit=10)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: InMemoryEmbeddingStore._candidates raised: {exc}")
    refs = _hit_refs(cand)
    assert ("out", "out#0") not in refs, (
        "US-03: out-of-scope record leaked from _candidates — store accepted `scope` but "
        "did not filter at query time (retrieve-then-filter false-green)"
    )
    assert ("in", "in#0") in refs, "in-scope record must be returned by _candidates"

    try:
        hits = store.query(qv, scope=scope, limit=10)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: InMemoryEmbeddingStore.query raised: {exc}")
    qrefs = _hit_refs(hits)
    assert ("out", "out#0") not in qrefs, (
        "US-03: out-of-scope record leaked from query() (post-filter after retrieve)"
    )
    assert ("in", "in#0") in qrefs, "in-scope record must be returned by query()"


def test_b3_unknown_entity_type_fails_closed():
    """ADR#3 (@架构 seq3216 / @需求 3211-6): undefined entity_type => deny-all (0 results)."""
    inmem = _require("InMemoryEmbeddingStore")
    scope_cls = _require("ScopeFilter")
    store = inmem()
    try:
        store.upsert([
            _make_record(doc_ref="in", chunk_ref="in#0", embedding=[1.0, 0.0, 0.0],
                         entity_scope=7, dim=3),
        ])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: InMemoryEmbeddingStore.upsert failed: {exc}")
    # an unregistered entity_type must resolve to the empty scope (fail-closed)
    unknown = _make_scope(scope_cls, entity_type="__unregistered__", ids=[])
    try:
        hits = store.query([1.0, 0.0, 0.0], scope=unknown, limit=10)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: query() raised for unknown entity_type: {exc}")
    assert not _hit_refs(hits), (
        "US-03 fail-closed: unknown entity_type must yield 0 results, not放行"
    )


class _StubHostSession:
    """Minimal Session-like: `execute(...).all()` yields one host row.

    Used to prove the *dispatcher itself* can return a non-empty set for a
    registered entity_type with the SAME actor/db it is asked about an
    unregistered one — so the fail-closed assertion cannot pass vacuously.
    """

    _ROWS = [(1, "h-stub", "10.0.0.1")]

    def execute(self, *args, **kwargs):
        rows = self._ROWS

        class _R:
            def all(self_inner):
                return list(rows)

            def __iter__(self_inner):
                return iter(list(rows))

        return _R()

    def scalar(self, *args, **kwargs):
        return len(self._ROWS)


class _AdminActor:
    is_admin = True
    id = 1
    visible_group_ids = [1]


def test_b3b_dispatcher_unknown_entity_type_fails_closed():
    """US-03 ⑥ (@架构 seq3242 / @需求 seq3235): the *dispatcher* — not a hand-built
    empty scope — must fail closed for an unregistered entity_type. A fail-open
    dispatcher (unknown => 全量 ids) MUST fail HERE.

    Non-vacuity sanity: with the SAME admin actor + stub session, a *known*
    entity_type (`host`) must return a non-empty visible set ⇒ proves fail-closed is
    per-type, not merely «this actor has no visible domain». Rejecting (raising) for
    the unknown type is also accepted as fail-closed.

    Degradation note (⑦-adjacent, @架构 seq3242): if the dispatcher exposes only
    `(entity_type, actor)` with no `db`, the offline positive control cannot be
    constructed here; in that case this case proves ONLY «unknown => empty» and does
    NOT prove the actor's visible domain.
    """
    fn = _require("visible_entity_ids_for")
    actor = _AdminActor()
    db = _StubHostSession()

    params = list(inspect.signature(fn).parameters)
    can_control_db = len(params) >= 3
    if can_control_db:
        def call(et):
            return fn(et, actor, db)
    else:
        def call(et):
            return fn(et, actor)

    positive = set()
    try:
        positive = set(call("host") or ())
    except Exception:  # noqa: BLE001
        positive = set()
    if can_control_db:
        assert positive, (
            "US-03 non-vacuity sanity: a known entity_type (`host`) must yield a "
            "non-empty visible set for this actor/db, else the fail-closed check below "
            "is vacuous"
        )

    try:
        unknown = call("__unregistered__")
    except Exception:  # noqa: BLE001
        return  # explicit rejection == fail-closed (acceptable)
    unknown_ids = set(unknown or ())
    assert not unknown_ids, (
        "US-03 fail-closed: dispatcher must return the empty set for an unregistered "
        f"entity_type, not widen to visible ids; got {sorted(unknown_ids)}"
    )


# ── B4: PG query-layer filter is structural (offline, no real PG) ────────────

class _FakeResult:
    def all(self):
        return []

    def scalars(self):
        return self

    def mappings(self):
        return self

    def fetchall(self):
        return []

    def first(self):
        return None

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


class _FakeSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return _FakeResult()

    def scalar(self, *args, **kwargs):
        return None

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _compiled_sql(fake) -> str:
    from sqlalchemy.dialects import postgresql  # noqa: PLC0415

    dialect = postgresql.dialect()
    out = []
    for st in fake.statements:
        try:
            out.append(str(st.compile(dialect=dialect, compile_kwargs={"literal_binds": True})))
        except Exception:  # noqa: BLE001
            try:
                out.append(str(st.compile(dialect=dialect)))
            except Exception:  # noqa: BLE001
                continue
    return " ".join(out).lower()


def _run_pg_candidates(cls, scope_cls, ids: list[int]) -> str:
    fake = _FakeSession()
    try:
        store = cls(session_factory=lambda: fake)
    except TypeError as exc:
        pytest.fail(
            "PostgresArrayEmbeddingStore must accept `session_factory` injection "
            f"(@架构 seq3222): {exc}"
        )
    scope = _make_scope(scope_cls, entity_type="host", ids=ids)
    try:
        store._candidates(query_vector=[1.0, 0.0, 0.0], scope=scope, limit=10)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock: PG _candidates raised against the fake session: {exc}")
    assert fake.statements, (
        "PG `_candidates` did not execute a statement via session_factory "
        "(query-layer filter unobservable)"
    )
    return _compiled_sql(fake)


def test_b4_pg_store_filters_in_query_layer():
    """@架构 seq3222/seq3230 (ADR#3 PG 查层判据): `PostgresArrayEmbeddingStore` must
    inject a `session_factory`, and `_candidates` must emit a SELECT whose compiled
    PostgreSQL carries an `entity_scope` **predicate** (IN/ANY) with the ACTUAL
    `scope.entity_ids` bound — and the bound set must DIFFER across scopes
    (defeats empty-`IN` / hardcoded-id structural false-greens).

    Offline: a fake session captures the executed statement. No real PG/extension.
    """
    cls = _require("PostgresArrayEmbeddingStore")
    scope_cls = _require("ScopeFilter")

    joined_a = _run_pg_candidates(cls, scope_cls, [700001, 700002])
    assert "entity_scope" in joined_a, (
        "PG query-layer filter missing: compiled statement has no `entity_scope` predicate "
        f"(retrieve-then-filter?); compiled={joined_a[:400]}"
    )
    assert (" in " in joined_a) or ("= any" in joined_a) or ("any(" in joined_a), (
        f"PG filter must be an IN/ANY predicate on entity_scope; compiled={joined_a[:400]}"
    )
    assert ("700001" in joined_a) and ("700002" in joined_a), (
        "PG filter must BIND the actual scope.entity_ids values (literal_binds / params); "
        f"compiled={joined_a[:400]}"
    )

    joined_b = _run_pg_candidates(cls, scope_cls, [900001])
    assert "900001" in joined_b, (
        f"second scope's entity_ids must be bound too; compiled={joined_b[:400]}"
    )
    assert "900001" not in joined_a and "700001" not in joined_b, (
        "IN bound values must VARY with scope (defeats empty-IN/hardcoded-id false-greens)"
    )


def test_b5_embedding_store_config_key_symbols():
    """@架构 seq3230 / @需求 seq3231: named config symbol + enum values + default
    `pg_array`, seeded in DEFAULT_CONFIG_RULES (add-only; NOT an ai.* flag)."""
    mod = _try("app.services.embedding_store")
    if isinstance(mod, Exception):
        pytest.fail(f"P4 lock: app.services.embedding_store unavailable: {mod}")
    key = getattr(mod, "EMBEDDING_STORE_CONFIG_KEY", None)
    pg = getattr(mod, "EMBEDDING_STORE_PG_ARRAY", None)
    mem = getattr(mod, "EMBEDDING_STORE_IN_MEMORY", None)
    assert key == "ai.embedding_store", f"EMBEDDING_STORE_CONFIG_KEY must be 'ai.embedding_store'; got {key!r}"
    assert pg and mem and pg != mem, f"enum values must be defined and distinct; pg={pg!r} in_memory={mem!r}"
    assert key not in AI_FLAGS, "`ai.embedding_store` is an enum, not one of the ai.* flags"

    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P4 lock: app.db.seed unavailable: {seed}")
    rules = getattr(seed, "DEFAULT_CONFIG_RULES", {})
    entry = rules.get(key)
    assert entry is not None, f"`{key}` must be seeded in DEFAULT_CONFIG_RULES (add-only)"
    assert entry.get("value") == pg, (
        f"`{key}` default must be `pg_array` ({pg!r}); got {entry.get('value')!r}"
    )


# ── ⑧ store resolver / fail-fast (@架构 seq3248) ──────────────────────────────

def _emb_mod():
    mod = _try("app.services.embedding_store")
    if isinstance(mod, Exception):
        pytest.fail(f"P4 lock ⑧: app.services.embedding_store unavailable: {mod}")
    return mod


def _call_build(build, db, value):
    for call in (
        lambda: build(db, value=value),
        lambda: build(db, value),
        lambda: build(value),
    ):
        try:
            return call()
        except TypeError:
            continue
    return build(db, value=value)


def _no_hardcoded_pg_store() -> bool:
    """⑧: `PostgresArrayEmbeddingStore(` must be constructed only in embedding_store.py."""
    try:
        import app  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    root = pathlib.Path(app.__file__).resolve().parent
    allowed = (root / "services" / "embedding_store.py").resolve()
    for py in root.rglob("*.py"):
        if py.resolve() == allowed:
            continue
        try:
            txt = py.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        if re.search(r"\bPostgresArrayEmbeddingStore\s*\(", txt):
            return False
    return True


def test_s9_store_resolver_symbols():
    """⑧ @架构 seq3248: named resolver/builder + VALID_STORES tuple."""
    mod = _emb_mod()
    for name in ("resolve_store_config", "build_embedding_store"):
        assert callable(getattr(mod, name, None)), (
            f"P4 lock ⑧: embedding_store.{name} must be defined"
        )
    valid = getattr(mod, "VALID_STORES", None)
    pg = getattr(mod, "EMBEDDING_STORE_PG_ARRAY", None)
    mem = getattr(mod, "EMBEDDING_STORE_IN_MEMORY", None)
    assert valid and pg and mem, "P4 lock ⑧: VALID_STORES + both enum values required"
    assert set(valid) == {pg, mem}, (
        f"VALID_STORES must be exactly {{{pg!r}, {mem!r}}}; got {valid!r}"
    )


def test_f2_resolve_store_config_default_and_invalid(monkeypatch):
    """⑧: default => pg_array; an invalid configured value => raise (no silent fallback)."""
    mod = _emb_mod()
    resolve = getattr(mod, "resolve_store_config", None)
    if resolve is None:
        pytest.fail("P4 lock ⑧: resolve_store_config missing")
    pg = getattr(mod, "EMBEDDING_STORE_PG_ARRAY", "pg_array")

    try:
        default = resolve()
    except TypeError:
        default = resolve(None)
    assert default == pg, f"resolve_store_config default must be {pg!r}; got {default!r}"

    repo = _try("app.repositories")
    cls = None if isinstance(repo, Exception) else getattr(repo, "ConfigRuleRepository", None)
    if cls is None or not hasattr(cls, "by_key"):
        pytest.fail("P4 lock ⑧: ConfigRuleRepository.by_key unavailable to drive invalid-config")

    class _Row:
        rule_value = {"value": "__bogus_store__"}

    monkeypatch.setattr(cls, "by_key", lambda self, *a, **k: _Row(), raising=False)
    try:
        resolve(object())
    except AssertionError:
        raise
    except Exception:  # noqa: BLE001
        return
    pytest.fail("resolve_store_config must RAISE for an invalid configured value")


def test_f3_build_embedding_store_dispatch_and_no_hardcode():
    """⑧: build dispatches by value; invalid => raise; no PG store hardcode outside the seam."""
    mod = _emb_mod()
    build = getattr(mod, "build_embedding_store", None)
    if build is None:
        pytest.fail("P4 lock ⑧: build_embedding_store missing")
    pg = getattr(mod, "EMBEDDING_STORE_PG_ARRAY", "pg_array")
    mem = getattr(mod, "EMBEDDING_STORE_IN_MEMORY", "in_memory")
    inmem_cls = _require("InMemoryEmbeddingStore")
    pg_cls = _require("PostgresArrayEmbeddingStore")

    got_mem = _call_build(build, None, mem)
    assert isinstance(got_mem, inmem_cls), (
        f"build_embedding_store({mem!r}) must return InMemoryEmbeddingStore; "
        f"got {type(got_mem)!r}"
    )

    got_pg = _call_build(build, lambda: _FakeSession(), pg)
    assert isinstance(got_pg, pg_cls), (
        f"build_embedding_store({pg!r}) must return PostgresArrayEmbeddingStore; "
        f"got {type(got_pg)!r}"
    )

    try:
        _call_build(build, lambda: _FakeSession(), "__bogus_store__")
    except Exception:  # noqa: BLE001
        pass
    else:
        pytest.fail("build_embedding_store must RAISE on an invalid value (no silent fallback)")

    assert _no_hardcoded_pg_store(), (
        "⑧: `PostgresArrayEmbeddingStore(` must not be constructed outside "
        "embedding_store.py (ai_service must call build_embedding_store)"
    )


# ── ⑨ NULL entity_scope must be fail-closed (@架构 seq3244/3250) ─────────────

def test_b6_null_entity_scope_fail_closed():
    """⑨: kb_embedding.entity_scope NOT NULL; a NULL/absent scope never matches a
    non-empty scope (InMemory behaviour + the PG compiled predicate)."""
    t = _tables().get("kb_embedding")
    if t is None:
        pytest.fail("P4 lock ⑨: table `kb_embedding` missing")
    col = t.columns.get("entity_scope")
    assert col is not None, "P4 lock ⑨: kb_embedding.entity_scope missing"
    assert col.nullable is False, (
        "⑨ fail-closed: kb_embedding.entity_scope must be nullable=False (no NULL=global)"
    )

    inmem = _require("InMemoryEmbeddingStore")
    scope_cls = _require("ScopeFilter")
    store = inmem()
    try:
        store.upsert([
            _make_record(doc_ref="nul", chunk_ref="nul#0", embedding=[1.0, 0.0, 0.0],
                         entity_scope=None, dim=3),
        ])
    except Exception:  # noqa: BLE001
        pass  # rejecting NULL at ingest is also fail-closed
    try:
        hits = store.query([1.0, 0.0, 0.0],
                           scope=_make_scope(scope_cls, entity_type="host", ids=[7]), limit=10)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock ⑨: InMemory query raised: {exc}")
    assert ("nul", "nul#0") not in _hit_refs(hits), (
        "⑨ fail-closed: a NULL/absent entity_scope chunk must NOT match a non-empty scope"
    )

    pg_cls = _require("PostgresArrayEmbeddingStore")
    sql = _run_pg_candidates(pg_cls, scope_cls, [7])
    assert "entity_scope is null" not in sql, (
        "⑨ fail-closed: PG predicate must not treat NULL entity_scope as global "
        f"(no `entity_scope IS NULL` pass branch); compiled={sql[:300]}"
    )


class _CaptureSession:
    """Captures `session.add(obj)` so the PG write path is observable offline."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def close(self):
        pass

    def execute(self, *a, **k):
        return _FakeResult()


def test_b6b_entity_scope_write_normalized_and_admin_read():
    """⑨ (@架构 seq3252): a falsy scope is WRITTEN as `[]` (NOT NULL); a no-scope
    record stays visible ONLY to `scope=None` (admin all-visible), never to a
    non-empty scope (the read-side fail-closed is pinned by b6)."""
    pg_cls = _require("PostgresArrayEmbeddingStore")
    cap = _CaptureSession()
    store = pg_cls(cap)
    try:
        store.upsert([{"doc_ref": "w", "chunk_ref": "w#0", "embedding": [1.0], "dim": 1}])
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P4 lock ⑨: PG upsert (write path) raised: {exc}")
    assert cap.added, "⑨: PG upsert must construct a KbEmbedding row"
    written = getattr(cap.added[0], "entity_scope", "MISSING")
    assert written is not None and written != "MISSING", (
        "⑨ write-path: a falsy/absent scope must be normalized to [] (NOT NULL), "
        f"not None; got {written!r}"
    )
    assert list(written) == [], f"⑨ write-path: falsy scope must store [] (got {written!r})"

    inmem = _require("InMemoryEmbeddingStore")
    store2 = inmem()
    store2.upsert([
        _make_record(doc_ref="g", chunk_ref="g#0", embedding=[1.0, 0.0],
                     entity_scope=None, dim=2),
    ])
    admin_hits = store2.query([1.0, 0.0], scope=None, limit=10)
    assert ("g", "g#0") in _hit_refs(admin_hits), (
        "⑨ read-path: `scope=None` (admin all-visible) must STILL return a no-scope "
        "record — do not fail-close the admin bypass"
    )


# ── ⑨/甲 service-layer scope dispatch (@架构 seq3252/3254) ───────────────────

class _AdminActor2:
    is_admin = True
    id = 1
    visible_group_ids = [1]


class _PlainActor:
    is_admin = False
    id = 2
    visible_group_ids = []


def test_b7_scope_for_failclosed_and_admin_bypass():
    """(甲) @架构 seq3254: `_scope_for` validates entity_type BEFORE the admin bypass —
    unknown type => non-None EMPTY scope for ALL roles (fail-closed); known + admin =>
    None (all-visible); non-admin must NEVER yield None (fail-open guard)."""
    svc = _try("app.services.ai_service")
    if isinstance(svc, Exception):
        pytest.fail(f"P4 lock ⑨/甲: app.services.ai_service unavailable: {svc}")
    scope_for = getattr(svc, "_scope_for", None)
    if scope_for is None:
        pytest.fail("P4 lock ⑨/甲: ai_service._scope_for missing")
    db = _FakeSession()

    admin_unknown = scope_for(db, _AdminActor2(), "__unregistered__")
    assert admin_unknown is not None, (
        "甲 fail-closed: admin + unknown entity_type must NOT be None/all-visible"
    )
    assert not set(admin_unknown.entity_ids), (
        "甲 fail-closed: admin + unknown entity_type must yield an EMPTY scope"
    )

    user_unknown = scope_for(db, _PlainActor(), "__unregistered__")
    assert user_unknown is not None and not set(user_unknown.entity_ids), (
        "甲 fail-closed: non-admin + unknown entity_type must yield a non-None empty scope"
    )

    assert scope_for(db, _AdminActor2(), "audit") is None, (
        "甲: known entity_type + admin must remain all-visible (scope=None)"
    )

    user_known = scope_for(db, _PlainActor(), "audit")
    assert user_known is not None, (
        "⑨ @架构 seq3252: a non-admin call must NEVER produce scope=None (fail-open guard)"
    )


# ── ④ FTS scope comparison must be str-cast (@架构 seq3250/3252) ─────────────

def test_s10_fts_scope_uses_str_cast():
    """④: `_fts_hits` must compare scope ids as strings — no `int()` (host ip/hostname
    enter the scope) and no `integer = text` PG error."""
    svc = _try("app.services.ai_service")
    if isinstance(svc, Exception):
        pytest.fail(f"P4 lock ④: app.services.ai_service unavailable: {svc}")
    fts = getattr(svc, "_fts_hits", None)
    if fts is None:
        pytest.fail("P4 lock ④: ai_service._fts_hits missing")
    assert "int(" not in inspect.getsource(fts), (
        "④: `_fts_hits` must not coerce scope ids with int() (v1.2: all str; host "
        "ip/hostname are non-numeric)"
    )

    scope_cls = _require("ScopeFilter")
    scope = _make_scope(scope_cls, entity_type="kb", ids=["10.0.0.1", "web-01"])
    try:
        out = fts(_FakeSession(), "q", scope, "kb", 5)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"④: `_fts_hits` must not raise on non-numeric scope ids: {exc}")
    assert isinstance(out, list)
