r"""P3 (工单 P3-1 ＋ 知识库 P3-2) contract locks — @单元测试工程师 (lock-first).

Frozen contract: @架构 P3a tuple **v1.2 终稿** (v1.1 = seq2580 + paths 勘误 seq2581
`109→129` + 残差 seq2586; v1.2 = seq2591/§25 seq2589 ⑥⑦⑧⑨ + seq2594 ⑩) ;
docs/api-design-v3.md §5/§6 ; docs/architecture-phase23.md §7/§8.
Baseline = release **`cfce18f`** (tree ≡ `3dea139`).

EXPECTED: clean **RED** until the P3 backend lands (add-only); import-guarded so the
run reports assertion failures rather than collection errors.

Scope of THIS lock (name-stable surface only)
---------------------------------------------
P1  ticket 13 权限码 ∈ seed `PERMISSION_TREE`
P2  kb 11 权限码 ∈ seed `PERMISSION_TREE`
A1  openapi: 20 new URL keys present with correct methods (P3-1 12 + P3-2 8)
A2  openapi `paths` grows 109 -> >=129 (monotonic; exact 129 re-pinned in
    `test_contract_openapi.py` per tuple §3 — OpenAPI `paths` is URL-keyed)
M1  tables: ticket / ticket_comment / ticket_attachment / ticket_ref /
    kb_article / kb_article_version / kb_category / kb_article_tag
M2  core columns (ticket / ticket_comment / ticket_attachment / ticket_ref /
    kb_article / kb_article_version / kb_category / kb_article_tag)
F1  feature.ticket / feature.kb default **False** in `DEFAULT_CONFIG_RULES`
F2  `"ticket" ∈ MON_NOTIFY_SCENES` (P3 add-only, @架构 seq2594 ⑩)
T1  `app.db.models.ticket.TICKET_REF_TYPES` membership == 6 (union of the two docs)
T2  `app.db.models.kb.KB_VISIBILITIES` membership == {public,internal,classified}
T3  `app.db.models.ticket.TICKET_STATUSES` closed set (reopen is an action)
T4  `app.services.ticket_service.TICKET_TRANSITIONS` action-keyed table; `allowed_from`
    compared as a SET (seq2605 §三 / seq2612 顺序非契约)
T5  `app.db.models.ticket.TICKET_EDITABLE_STATUSES` membership == {create,assign}
T6  `app.db.models.ticket.TICKET_CATEGORIES` membership (req seq2608)
T7  `app.db.models.ticket.TICKET_PRIORITIES` membership (req seq2608)
B1  `app.services.kb_service.KB_CATEGORY_MAX_DEPTH` == 3
P3.1 工单编号 (human business key; tuple v1 @架构 seq2739; branch `p3-1-ticket-no`):
    N1 `ticket.ticket_no` NOT NULL + unique index `uq_ticket_ticket_no` (M2 追加)
    N2 `TicketOut` 暴露只读 `ticket_no`; `TicketCreate`/`TicketUpdate` **不含**
    N3 `GET /tickets` 增可选 `?ticket_no=` 过滤（路由不增 ⇒ paths 恒 129）
    N4 不可变：创建后编辑 `category` ⇒ `ticket_no` 不变（双层保险）
    N5 生成器格式 `^TK-\d{8}-\d{3,}$`、全局单序列 `seq_ticket_no`
       （生成器守卫见 `test_no_generation_guards.py`）
(symbols pinned by @架构 seq2605 终裁: **enums live in `app/db/models/`**, not
 service — MON_*/EXEC_STATUSES/AUTH_PROVIDER_TYPES precedent; only the transition
 map lives in the service.)

Route-level negative locks ⑥/⑨ (added once the P3 routers landed): over the already
pinned route keys + permission codes, via an in-process TestClient — the HTTP status
is the contract, NOT function names (seq2605 §四):
⑥  POST /tickets with `assignee_id` needs ticket:create AND ticket:assign
    => 403 when ticket:assign is absent.
⑨  POST /kb/categories with a parent already at KB_CATEGORY_MAX_DEPTH => 422.

Run (from the backend checkout, backend venv):
    python -m pytest tests/test_p3_ticket_kb_contract_lock.py -p no:cacheprovider -o addopts= -q
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


# ── P1/P2: permission codes (seed PERMISSION_TREE) ───────────────────────────

TICKET_PERMS = {
    "ticket:list",
    "ticket:create",
    "ticket:edit",
    "ticket:assign",
    "ticket:accept",
    "ticket:process",
    "ticket:done",
    "ticket:close",
    "ticket:reopen",
    "ticket:cancel",
    "ticket:comment",
    "ticket:attachment",
    "ticket:ref",
}
KB_PERMS = {
    "kb:article:list",
    "kb:article:add",
    "kb:article:edit",
    "kb:article:del",
    "kb:article:version",
    "kb:article:rollback",
    "kb:category:list",
    "kb:category:add",
    "kb:category:edit",
    "kb:category:del",
    "kb:search",
}


def _perm_codes() -> set[str]:
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3 lock: app.db.seed unavailable: {seed}")
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_ticket_permission_codes_registered():
    missing = TICKET_PERMS - _perm_codes()
    assert not missing, f"ticket permission codes missing from PERMISSION_TREE: {sorted(missing)}"


def test_p2_kb_permission_codes_registered():
    missing = KB_PERMS - _perm_codes()
    assert not missing, f"kb permission codes missing from PERMISSION_TREE: {sorted(missing)}"


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

P3_TICKET_PATHS = {
    "/api/v1/tickets": {"get", "post"},
    "/api/v1/tickets/{ticket_id}": {"get", "put"},
    "/api/v1/tickets/{ticket_id}/assign": {"post"},
    "/api/v1/tickets/{ticket_id}/accept": {"post"},
    "/api/v1/tickets/{ticket_id}/process": {"post"},
    "/api/v1/tickets/{ticket_id}/done": {"post"},
    "/api/v1/tickets/{ticket_id}/close": {"post"},
    "/api/v1/tickets/{ticket_id}/reopen": {"post"},
    "/api/v1/tickets/{ticket_id}/cancel": {"post"},
    "/api/v1/tickets/{ticket_id}/comments": {"post"},
    "/api/v1/tickets/{ticket_id}/attachments": {"post"},
    "/api/v1/tickets/{ticket_id}/refs": {"post"},
}
P3_KB_PATHS = {
    "/api/v1/kb/articles": {"get", "post"},
    "/api/v1/kb/articles/{article_id}": {"get", "put", "delete"},
    "/api/v1/kb/articles/{article_id}/versions": {"get"},
    "/api/v1/kb/articles/{article_id}/versions/{version}": {"get"},
    "/api/v1/kb/articles/{article_id}/rollback": {"post"},
    "/api/v1/kb/categories": {"get", "post"},
    "/api/v1/kb/categories/{category_id}": {"put", "delete"},
    "/api/v1/kb/search": {"get"},
}
_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p3_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for key, methods in {**P3_TICKET_PATHS, **P3_KB_PATHS}.items():
        item = paths.get(key)
        if item is None:
            problems.append(f"missing {key}")
            continue
        have = {m for m in item if m in _METHODS}
        miss = methods - have
        if miss:
            problems.append(f"{key} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P3 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_grows_to_129():
    paths = _openapi_paths()
    assert len(paths) >= 129, (
        f"P3 must add 20 URL keys (109 -> 129); got {len(paths)}. "
        "OpenAPI `paths` is URL-keyed; exact count re-pinned in test_contract_openapi.py."
    )


# ── M1/M2: SQLAlchemy tables & core columns ──────────────────────────────────

P3_TABLES = {
    "ticket",
    "ticket_comment",
    "ticket_attachment",
    "ticket_ref",
    "kb_article",
    "kb_article_version",
    "kb_category",
    "kb_article_tag",
}
CORE_COLUMNS = {
    "ticket": {"title", "category", "priority", "status", "requester_id", "assignee_id", "sla_due_at", "ticket_no"},
    "ticket_comment": {"ticket_id", "content"},
    "ticket_attachment": {"ticket_id", "file_id"},
    "ticket_ref": {"ticket_id", "ref_type", "ref_id"},
    "kb_article": {"title", "category_id", "visibility", "current_version"},
    "kb_article_version": {"article_id", "version", "content"},
    "kb_category": {"parent_id"},
    "kb_article_tag": {"article_id"},
}


def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415  (register all models)
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_p3_tables_registered():
    missing = P3_TABLES - set(_tables())
    assert not missing, f"P3 tables missing: {sorted(missing)}"


def test_m2_core_columns_present():
    tables = _tables()
    problems = []
    for tname, cols in CORE_COLUMNS.items():
        t = tables.get(tname)
        if t is None:
            problems.append(f"table {tname} missing")
            continue
        miss = cols - set(t.columns.keys())
        if miss:
            problems.append(f"{tname} missing columns {sorted(miss)}")
    assert not problems, "P3 core columns incomplete: " + "; ".join(problems)


# ── F1: feature flags default off ────────────────────────────────────────────

def test_f1_feature_flags_default_false():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3 lock: app.db.seed unavailable: {seed}")
    rules = getattr(seed, "DEFAULT_CONFIG_RULES", {})
    problems = []
    for key in ("feature.ticket", "feature.kb"):
        entry = rules.get(key)
        if entry is None:
            problems.append(f"{key} not seeded in DEFAULT_CONFIG_RULES")
        elif entry.get("value") is not False:
            problems.append(f"{key} default must be False; got {entry.get('value')!r}")
    assert not problems, "P3 feature flags: " + "; ".join(problems)


# ── F2: notify scene add-only (@架构 seq2594 ⑩) ──────────────────────────────

def test_f2_notify_scene_ticket_registered():
    mod = _try("app.db.models.monitor")
    if isinstance(mod, Exception):
        pytest.fail(f"P3 lock: app.db.models.monitor unavailable: {mod}")
    scenes = tuple(getattr(mod, "MON_NOTIFY_SCENES", ()))
    assert "ticket" in scenes, (
        f"P3 must add 'ticket' to MON_NOTIFY_SCENES (add-only, @架构 seq2594 ⑩); got {scenes}"
    )


# ── T*/B*: enum tuples & state machine (symbols pinned by @架构 seq2605) ──────

TICKET_REF_TYPES = {"exec_task", "approval", "asset_host", "script", "schedule", "kb_article"}
TICKET_CATEGORIES = {"incident", "change", "request", "other"}
TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}
KB_VISIBILITIES = {"public", "internal", "classified"}
TICKET_STATUSES = {"create", "assign", "accept", "processing", "done", "close", "cancel"}
TICKET_EDITABLE_STATUSES = {"create", "assign"}
TICKET_TRANSITIONS = {
    "assign": ({"create", "assign"}, "assign"),
    "accept": ({"assign"}, "accept"),
    "process": ({"accept"}, "processing"),
    "done": ({"processing"}, "done"),
    "close": ({"done"}, "close"),
    "reopen": ({"done", "close"}, "processing"),
    "cancel": ({"create", "assign", "accept", "processing"}, "cancel"),
}
KB_CATEGORY_MAX_DEPTH = 3


def _const(mod: str, name: str):
    m = _try(mod)
    if isinstance(m, Exception):
        pytest.fail(f"P3 lock: {mod} unavailable: {m}")
    if not hasattr(m, name):
        pytest.fail(f"P3 lock: {mod}.{name} missing (EXPECTED RED until P3 lands)")
    return getattr(m, name)


def _norm_transitions(t) -> dict:
    return {a: (frozenset(frm), tgt) for a, (frm, tgt) in dict(t).items()}


def test_t1_ticket_ref_types_frozen():
    got = set(_const("app.db.models.ticket", "TICKET_REF_TYPES"))
    assert got == TICKET_REF_TYPES, (
        "TICKET_REF_TYPES membership (v1.2 union; req seq2608). "
        f"NOTE: seq2605 tuple-order vs seq2608 union-order differ on script/schedule — "
        f"membership locked, order NOT asserted. missing={sorted(TICKET_REF_TYPES - got)} "
        f"extra={sorted(got - TICKET_REF_TYPES)}"
    )


def test_t6_ticket_categories_frozen():
    got = set(_const("app.db.models.ticket", "TICKET_CATEGORIES"))
    assert got == TICKET_CATEGORIES, (
        f"TICKET_CATEGORIES (req seq2608): {sorted(TICKET_CATEGORIES)}; got {sorted(got)}"
    )


def test_t7_ticket_priorities_frozen():
    got = set(_const("app.db.models.ticket", "TICKET_PRIORITIES"))
    assert got == TICKET_PRIORITIES, (
        f"TICKET_PRIORITIES (req seq2608): {sorted(TICKET_PRIORITIES)}; got {sorted(got)}"
    )


def test_t2_kb_visibilities_frozen():
    got = set(_const("app.db.models.kb", "KB_VISIBILITIES"))
    assert got == KB_VISIBILITIES, f"KB_VISIBILITIES (§25): {sorted(KB_VISIBILITIES)}; got {sorted(got)}"


def test_t3_ticket_statuses_closed_set():
    got = set(_const("app.db.models.ticket", "TICKET_STATUSES"))
    assert got == TICKET_STATUSES, (
        f"TICKET_STATUSES closed set (reopen is an action): {sorted(TICKET_STATUSES)}; got {sorted(got)}"
    )


def test_t4_ticket_transition_table():
    got = _norm_transitions(_const("app.services.ticket_service", "TICKET_TRANSITIONS"))
    assert got == TICKET_TRANSITIONS, (
        "TICKET_TRANSITIONS must be action-keyed dict[action -> (allowed_from, target)] per seq2605 §三; "
        f"keys_missing={sorted(set(TICKET_TRANSITIONS) - set(got))} "
        f"keys_extra={sorted(set(got) - set(TICKET_TRANSITIONS))} "
        f"mismatch={[a for a in TICKET_TRANSITIONS if a in got and got[a] != TICKET_TRANSITIONS[a]]}"
    )


def test_t5_ticket_editable_statuses():
    got = set(_const("app.db.models.ticket", "TICKET_EDITABLE_STATUSES"))
    assert got == TICKET_EDITABLE_STATUSES, (
        f"TICKET_EDITABLE_STATUSES must be {sorted(TICKET_EDITABLE_STATUSES)} (edit only pre-accept); got {sorted(got)}"
    )


def test_b1_kb_category_max_depth():
    got = _const("app.services.kb_service", "KB_CATEGORY_MAX_DEPTH")
    assert got == KB_CATEGORY_MAX_DEPTH, f"KB_CATEGORY_MAX_DEPTH must be {KB_CATEGORY_MAX_DEPTH}; got {got!r}"


# ── N1–N5: P3.1 工单编号 ticket_no (tuple v1 @架构 seq2739) ───────────────────

TICKET_NO_RE = re.compile(r"^TK-\d{8}-\d{3,}$")
TICKET_NO_UNIQUE_NAME = "uq_ticket_ticket_no"


def test_n1_ticket_no_not_null_and_unique_index():
    tables = _tables()
    t = tables.get("ticket")
    if t is None:
        pytest.fail("P3.1 lock: table 'ticket' missing")
    col = t.columns.get("ticket_no")
    if col is None:
        pytest.fail("P3.1 lock: ticket.ticket_no missing (EXPECTED RED until P3.1 lands)")
    assert col.nullable is False, "ticket_no must be NOT NULL"

    found = []
    for ix in t.indexes:
        if ix.name == TICKET_NO_UNIQUE_NAME:
            found.append(("index", bool(ix.unique), {c.name for c in ix.columns}))
    for cst in t.constraints:
        if getattr(cst, "name", None) == TICKET_NO_UNIQUE_NAME:
            found.append(("constraint", True, {c.name for c in cst.columns}))
    assert found, f"P3.1 lock: unique index/constraint {TICKET_NO_UNIQUE_NAME!r} missing on ticket"
    kind, uniq, cols = found[0]
    assert uniq and cols == {"ticket_no"}, (
        f"{TICKET_NO_UNIQUE_NAME} must be UNIQUE over exactly {{ticket_no}}; "
        f"got {kind} unique={uniq} cols={sorted(cols)}"
    )


def test_n2_ticket_no_readonly_not_in_create_or_update():
    from app.schemas.ticket import TicketCreate, TicketOut, TicketUpdate  # noqa: PLC0415

    assert "ticket_no" in TicketOut.model_fields, "TicketOut must expose read-only ticket_no"
    assert "ticket_no" not in TicketCreate.model_fields, (
        "ticket_no is server-generated; must NOT be client-settable via TicketCreate"
    )
    assert "ticket_no" not in TicketUpdate.model_fields, (
        "ticket_no is immutable; must NOT appear in TicketUpdate"
    )


def test_n3_list_filter_exposes_ticket_no_param():
    paths = _openapi_paths()
    item = paths.get("/api/v1/tickets")
    assert item is not None, "ticket list route missing"
    params = item.get("get", {}).get("parameters", []) or []
    names = {p.get("name") for p in params}
    assert "ticket_no" in names, (
        "GET /tickets must accept optional ?ticket_no= filter (mirror exec list_tasks); "
        f"params seen: {sorted(n for n in names if n)}"
    )


def test_n3b_paths_unchanged_129():
    paths = _openapi_paths()
    assert len(paths) == 129, (
        f"P3.1 adds no route (paths must stay 129); got {len(paths)}"
    )


# ── ⑥/⑨: route-level negative locks (in-process TestClient) ──────────────────
#
# Boots the *real* FastAPI app with three offline overrides (mirrors
# tests/integration/p2ss/conftest.py) so nothing external is touched:
#   * get_db           -> temp file SQLite session;
#   * SessionLocal     -> rebound to that engine (audit middleware writes offline);
#   * get_current_user -> a fake principal (permission set toggled per test).
# The app is used WITHOUT its lifespan, so run_seed / Redis never start.
# Assertions are HTTP-level (403 / 422) — the route + status is the contract.

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

# Every table ⑥/⑨ touch (plus FK targets); filtered by availability so the base
# (pre-P3) run still collects cleanly and reports assertion failures, not errors.
_P3_ROUTE_TABLES = (
    "config_rule",
    "sys_audit_log",
    "sys_user",
    "ticket",
    "ticket_comment",
    "ticket_attachment",
    "ticket_ref",
    "kb_article",
    "kb_article_version",
    "kb_category",
    "kb_article_tag",
)


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


def _route_tables():
    import app.db.models  # noqa: F401,PLC0415 (register all models on Base.metadata)
    from app.db.base import Base  # noqa: PLC0415

    tl = Base.metadata.tables
    return [tl[name] for name in _P3_ROUTE_TABLES if name in tl]


def _seed_depth3(session) -> int:
    """Seed a 3-deep kb category chain; returns the id of the depth-3 node."""
    try:
        from app.db.models.kb import KbCategory  # noqa: PLC0415
    except Exception:  # noqa: BLE001  (P3 models absent -> placeholder id)
        return 3
    c1 = KbCategory(parent_id=0, name="c1")
    session.add(c1)
    session.flush()
    c2 = KbCategory(parent_id=c1.id, name="c2")
    session.add(c2)
    session.flush()
    c3 = KbCategory(parent_id=c2.id, name="c3")
    session.add(c3)
    session.flush()
    return c3.id


@pytest.fixture()
def p3_route_client(tmp_path):
    """Yields ``(client, set_user, depth3_id)``. ``set_user(perms, admin=False)``."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p3route.db'}", future=True)
    Base.metadata.create_all(engine, tables=_route_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()

    # feature.* gate runs BEFORE the permission gate (service) -> must be ON,
    # else the response would be 400 rather than the asserted 403 / 422.
    try:
        from app.db.models.notify import ConfigRule  # noqa: PLC0415

        for key in ("feature.ticket", "feature.kb"):
            session.add(ConfigRule(rule_key=key, rule_value={"value": True}))
    except Exception:  # noqa: BLE001
        pass
    depth3 = _seed_depth3(session)
    session.commit()

    prev_bind = getattr(_dbs.SessionLocal, "kw", {}).get("bind")
    _dbs.SessionLocal.configure(bind=engine)

    import app.main as main  # noqa: PLC0415
    from app.api.deps import CurrentUser, get_current_user  # noqa: PLC0415
    from app.db.session import get_db  # noqa: PLC0415
    from starlette.testclient import TestClient  # noqa: PLC0415

    def _get_db():
        yield session

    main.app.dependency_overrides[get_db] = _get_db

    def set_user(perms, admin=False):
        user = CurrentUser(
            user_id=1, username="qa", is_admin=admin,
            permissions=list(perms), visible_group_ids=[],
        )
        main.app.dependency_overrides[get_current_user] = lambda: user
        return user

    try:
        yield TestClient(main.app), set_user, depth3
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_6_create_ticket_with_assignee_requires_ticket_assign_403(p3_route_client):
    client, set_user, _ = p3_route_client
    set_user(["ticket:create"])  # create yes, assign NO
    resp = client.post(
        "/api/v1/tickets",
        json={"title": "t6", "category": "incident", "priority": "low", "assignee_id": 2},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json().get("code") == 403


def test_9_kb_category_below_max_depth_422(p3_route_client):
    client, set_user, depth3 = p3_route_client
    set_user(["kb:category:add"])
    resp = client.post("/api/v1/kb/categories", json={"name": "too-deep", "parent_id": depth3})
    assert resp.status_code == 422, resp.text
    assert resp.json().get("code") == 422


def test_n4_ticket_no_immutable_on_category_edit(p3_route_client, monkeypatch):
    """N4: after create, editing ``category`` must leave ``ticket_no`` unchanged.

    The generator is monkeypatched (SQLite has no ``nextval``); this exercises the
    service's read-only exposure + immutability, not the sequence itself.
    """
    client, set_user, _ = p3_route_client
    from app.services import ticket_service  # noqa: PLC0415

    if not hasattr(ticket_service, "_ticket_no"):
        pytest.fail("P3.1 lock: ticket_service._ticket_no missing (EXPECTED RED until P3.1 lands)")
    monkeypatch.setattr(ticket_service, "_ticket_no", lambda db: "TK-20260924-001")

    set_user(["ticket:create", "ticket:edit"])
    created = client.post(
        "/api/v1/tickets",
        json={"title": "immutable", "category": "incident", "priority": "low"},
    )
    assert created.status_code == 200, created.text
    data = created.json()["data"]
    assert data.get("ticket_no") == "TK-20260924-001", (
        f"TicketOut must expose the generated ticket_no; got {data.get('ticket_no')!r}"
    )
    tid = data["id"]

    edited = client.put(f"/api/v1/tickets/{tid}", json={"category": "other"})
    assert edited.status_code == 200, edited.text
    edata = edited.json()["data"]
    assert edata.get("category") == "other", "edit must actually apply (guard must be meaningful)"
    assert edata.get("ticket_no") == "TK-20260924-001", (
        "editing category must NOT change ticket_no (immutable human key)"
    )
