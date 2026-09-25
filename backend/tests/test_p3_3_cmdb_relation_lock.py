r"""P3-3 CMDB 深化 (关系 / 拓扑 / 影响分析) contract locks — @单元测试工程师 (lock-first).

Frozen contract: @架构 **P3-3 tuple v0.2** (seq2808) ; design docs
`docs/architecture-phase23.md §12` (commit `2d05255`, branch `p3-scope-align`) ;
requirements `§27.1` (@需求 seq2800 细则 v0.1 + seq2803/2804 采纳).
Baseline = release **M2 = `38ee2ba`** (master).

Same-table reuse = **YES**: P3-3 defines the ONE relation truth source
`entity_relation` (NOT a second `cmdb_ci_relation`; §26 AIOps reuses this table).

EXPECTED: clean **RED** until the P3-3 backend lands (add-only); import-guarded so the
run reports assertion failures rather than collection errors. Nothing external is
touched (offline SQLite; no live PG/Redis, no migrations applied).

Scope of THIS lock (name-stable surface only)
---------------------------------------------
P1  asset relation/topo 权限码 ∈ seed `PERMISSION_TREE`
    {asset:relation:list, asset:relation:add, asset:relation:del, asset:topo:view}
A1  openapi: 4 new URL keys present with correct methods
A2  openapi `paths` == 133 (129 + 4 URL keys; URL-keyed, NOT operations)
    (@后端 seq2814 / @reviewer seq2816 / @集成 seq2815 — §27.1 #4)
M1  table `entity_relation` registered (same-table reuse; no `cmdb_ci_relation`)
M2  core columns of `entity_relation`
C1  UNIQUE(src_type, src_id, dst_type, dst_id, rel_type) — dedup directed edges
C2  CHECK 禁自环  NOT(src_type=dst_type AND src_id=dst_id)
X1  3 indexes: (src_type,src_id) / (dst_type,dst_id) / (rel_type)
F1  feature flag `feature.cmdb_topology` default **False** in `DEFAULT_CONFIG_RULES`
G1  migration: single head descending from `e1f2a3b4c5d7` (suggested rev `f2a3b4c5d6e7`)

Route-level behavioural locks (in-process TestClient, offline SQLite) — the HTTP status
/ response shape is the contract, NOT function names:
B1  POST /assets/relations is **idempotent** (repeat -> same response, HTTP 200, not 409)
B2  topology `depth` > hard cap 3 => 422 (KB-depth convention)
B3  GET /assets/cmdb/topology shape {nodes[], edges[], truncated}
B4  GET /assets/cmdb/impact shape {root, affected[], count}
B5  US-03 read: non-admin with no visible entities sees no topology nodes
B6  US-03 write: POST /assets/relations needs caller-visible src AND dst, else 403
    (§27.1 #6, @reviewer seq2811 / @集成 seq2812 / @后端 seq2814)
B7  DELETE /assets/relations/{id}: first delete 200 (Result), repeat/missing 404
    (@架构 tuple v0.4 seq2817 #2 — platform convention, 204 dropped)

Run (from the backend checkout, backend venv):
    python -m pytest tests/test_p3_3_cmdb_relation_lock.py -p no:cacheprovider -o addopts= -q
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

CMDB_PERMS = {
    "asset:relation:list",
    "asset:relation:add",
    "asset:relation:del",
    "asset:topo:view",
}


def _perm_codes() -> set[str]:
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-3 lock: app.db.seed unavailable: {seed}")
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_asset_relation_permission_codes_registered():
    missing = CMDB_PERMS - _perm_codes()
    assert not missing, (
        "P3-3 permission codes missing from PERMISSION_TREE "
        f"(reuse `asset:` namespace, do NOT open `cmdb:`): {sorted(missing)}"
    )


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

# URL-keyed expectations (GET+POST share one key for /assets/relations).
CMDB_PATHS = {
    "/api/v1/assets/relations": {"get", "post"},
    "/api/v1/assets/cmdb/topology": {"get"},
    "/api/v1/assets/cmdb/impact": {"get"},
}
# DELETE /assets/relations/{id}: path-param name is not contract-fixed -> matched by shape.
_REL_DELETE_RE = re.compile(r"^/api/v1/assets/relations/\{[^}]+\}$")
_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-3 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p3_3_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for key, methods in CMDB_PATHS.items():
        item = paths.get(key)
        if item is None:
            problems.append(f"missing {key}")
            continue
        have = {m for m in item if m in _METHODS}
        miss = methods - have
        if miss:
            problems.append(f"{key} missing methods {sorted(miss)} (have {sorted(have)})")
    del_keys = [k for k in paths if _REL_DELETE_RE.match(k)]
    if not del_keys:
        problems.append("missing /api/v1/assets/relations/{id}")
    else:
        ok = any("delete" in paths[k] for k in del_keys)
        if not ok:
            problems.append("DELETE /api/v1/assets/relations/{id} missing (have no delete)")
    assert not problems, "P3-3 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_133():
    paths = _openapi_paths()
    # P3-3 adds 4 URL keys => 129 -> 133. Later add-only batches (P3-4/P3-5)
    # legitimately raise the cumulative count; exact value re-pinned in
    # test_contract_openapi.py (mirrors the P3 lock's `>= 129` form).
    assert len(paths) >= 133, (
        f"P3-3 baseline (133) must not shrink; got {len(paths)}. "
        "OpenAPI `paths` is URL-keyed (GET+POST share one key)."
    )


# ── M1/M2: SQLAlchemy table & core columns ───────────────────────────────────

RELATION_TABLE = "entity_relation"
RELATION_COLUMNS = {
    "id",
    "src_type",
    "src_id",
    "dst_type",
    "dst_id",
    "rel_type",
    "properties",
    "remark",
    "created_by",
    "created_at",
    "updated_at",
}
REL_TYPE_SEED = {"depends_on", "runs_on", "connects_to", "member_of", "hosts"}


def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415  (register all models)
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-3 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_entity_relation_table_registered():
    tables = _tables()
    assert RELATION_TABLE in tables, (
        f"P3-3 must define `{RELATION_TABLE}` (same-table reuse = YES; §26 reuses it); "
        f"got tables: {sorted(t for t in tables if 'relation' in t or t in ('asset_host','asset_group'))}"
    )
    assert "cmdb_ci_relation" not in tables, (
        "tuple §B1: do NOT create a second `cmdb_ci_relation` table (double-build)"
    )


def test_m2_entity_relation_core_columns():
    t = _tables().get(RELATION_TABLE)
    if t is None:
        pytest.fail(f"P3-3 lock: table `{RELATION_TABLE}` missing (EXPECTED RED until P3-3 lands)")
    miss = RELATION_COLUMNS - set(t.columns.keys())
    assert not miss, f"{RELATION_TABLE} missing columns {sorted(miss)}"


# ── C1/C2/X1: constraints & indexes ──────────────────────────────────────────

def _relation_table():
    t = _tables().get(RELATION_TABLE)
    if t is None:
        pytest.fail(f"P3-3 lock: table `{RELATION_TABLE}` missing (EXPECTED RED until P3-3 lands)")
    return t


def test_c1_unique_five_tuple():
    from sqlalchemy import UniqueConstraint  # noqa: PLC0415

    t = _relation_table()
    want = {"src_type", "src_id", "dst_type", "dst_id", "rel_type"}
    found = []
    for cst in t.constraints:
        if isinstance(cst, UniqueConstraint) and {c.name for c in cst.columns} == want:
            found.append(cst)
    for ix in t.indexes:
        if ix.unique and {c.name for c in ix.columns} == want:
            found.append(ix)
    assert found, (
        "entity_relation must be UNIQUE over exactly "
        f"UNIQUE(src_type,src_id,dst_type,dst_id,rel_type) (dedup directed edges); "
        f"constraints={[type(c).__name__ for c in t.constraints]}"
    )


def test_c2_check_no_self_loop():
    from sqlalchemy import CheckConstraint  # noqa: PLC0415

    t = _relation_table()
    checks = [c for c in t.constraints if isinstance(c, CheckConstraint)]
    assert checks, "entity_relation must declare a CHECK 禁自环 (tuple §B3)"
    txt = " ".join(str(c.sqltext) for c in checks)
    assert "src_id" in txt and "dst_id" in txt, (
        f"self-loop CHECK must reference src_id/dst_id; got sqltext: {txt!r}"
    )


def test_x1_three_indexes():
    t = _relation_table()
    want = {("src_type", "src_id"), ("dst_type", "dst_id"), ("rel_type",)}
    have = {tuple(c.name for c in ix.columns) for ix in t.indexes}
    miss = want - have
    assert not miss, (
        f"entity_relation must index {sorted(want)}; "
        f"missing {sorted(miss)} (have {sorted(have)})"
    )


# ── F1: feature flag default off ─────────────────────────────────────────────

def test_f1_feature_cmdb_topology_default_false():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-3 lock: app.db.seed unavailable: {seed}")
    rules = getattr(seed, "DEFAULT_CONFIG_RULES", {})
    entry = rules.get("feature.cmdb_topology")
    assert entry is not None, "feature.cmdb_topology not seeded in DEFAULT_CONFIG_RULES"
    assert entry.get("value") is False, (
        f"feature.cmdb_topology default must be False; got {entry.get('value')!r}"
    )


# ── G1: migration single head descending from the P3.1 head ──────────────────

_VERSIONS_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "alembic" / "versions"
_P3X_HEAD = "e1f2a3b4c5d7"
_P33_HEAD = "f2a3b4c5d6e7"


def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    return revs


def test_g1_migration_single_head_descends_from_p3x():
    revs = _revision_graph()
    assert _P3X_HEAD in revs, f"P3.1 head {_P3X_HEAD} missing from versions dir"
    assert revs.get(_P33_HEAD) == _P3X_HEAD, (
        f"P3-3 migration must descend directly from {_P3X_HEAD}; got {revs.get(_P33_HEAD)!r}"
    )
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    head = heads[0]
    # Later add-only batches (P3-4/P3-5) extend the same linear chain ABOVE P3-3;
    # the head must still descend from the P3-3 rev (not necessarily equal it).
    seen: set[str] = set()
    cursor: str | None = head
    while cursor and cursor not in seen:
        seen.add(cursor)
        cursor = revs.get(cursor)
    assert _P33_HEAD in seen, (
        f"head {head} must descend from P3-3 {_P33_HEAD}; chain={sorted(seen)}"
    )


# ── B1–B5: route-level behavioural locks (offline TestClient) ─────────────────
#
# Boots the real FastAPI app with the same offline overrides used across the suite
# (mirrors test_p3_ticket_kb_contract_lock.py): temp-file SQLite; `get_db` ->
# session; `SessionLocal` rebound (audit middleware); `get_current_user` -> fake
# principal. The app is used WITHOUT its lifespan, so run_seed / Redis never start.

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_CORE_TABLES = (
    "config_rule",
    "sys_audit_log",
    "sys_user",
    "asset_group",
    "asset_host",
    RELATION_TABLE,
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


@pytest.fixture()
def p33_client(tmp_path):
    """Yields ``(client, set_user, host1_id, host2_id)``. ``set_user(perms, admin=False)``."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p33.db'}", future=True)
    Base.metadata.create_all(engine, tables=_core_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()

    h1 = h2 = None
    try:
        from app.db.models.asset import AssetGroup, Host  # noqa: PLC0415

        g = AssetGroup(parent_id=0, name="g")
        session.add(g)
        session.flush()
        h1 = Host(hostname="h1", ip="10.0.0.1", group_id=g.id)
        h2 = Host(hostname="h2", ip="10.0.0.2", group_id=g.id)
        session.add_all([h1, h2])
        session.flush()
        h1_id, h2_id = h1.id, h2.id
    except Exception:  # noqa: BLE001
        h1_id, h2_id = 1, 2

    # feature gate runs before the permission gate -> must be ON for the asserted status.
    try:
        from app.db.models.notify import ConfigRule  # noqa: PLC0415

        session.add(ConfigRule(rule_key="feature.cmdb_topology", rule_value={"value": True}))
    except Exception:  # noqa: BLE001
        pass
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
        yield TestClient(main.app), set_user, h1_id, h2_id
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_b1_post_relation_idempotent(p33_client):
    client, set_user, h1, h2 = p33_client
    set_user(["asset:relation:add"], admin=True)
    body = {"src_type": "host", "src_id": h1, "dst_type": "host", "dst_id": h2, "rel_type": "depends_on"}
    r1 = client.post("/api/v1/assets/relations", json=body)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/v1/assets/relations", json=body)
    assert r2.status_code == 200, (
        f"POST /assets/relations must be idempotent (repeat -> existing row, NOT 409); got {r2.status_code}"
    )
    assert r1.json().get("data") == r2.json().get("data"), (
        "idempotent POST must return the identical existing row on repeat"
    )


def test_b2_topology_depth_over_cap_422(p33_client):
    client, set_user, h1, _ = p33_client
    set_user(["asset:topo:view"], admin=True)
    r = client.get(
        "/api/v1/assets/cmdb/topology",
        params={"entity_type": "host", "entity_id": h1, "depth": 4},
    )
    assert r.status_code == 422, r.text
    assert r.json().get("code") == 422


def test_b3_topology_response_shape(p33_client):
    client, set_user, h1, _ = p33_client
    set_user(["asset:topo:view"], admin=True)
    r = client.get(
        "/api/v1/assets/cmdb/topology",
        params={"entity_type": "host", "entity_id": h1, "depth": 1},
    )
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"nodes", "edges", "truncated"} <= set(d), (
        f"topology must return {{nodes[], edges[], truncated}}; keys={sorted(d)}"
    )
    assert isinstance(d["nodes"], list) and isinstance(d["edges"], list)


def test_b4_impact_response_shape(p33_client):
    client, set_user, h1, _ = p33_client
    set_user(["asset:topo:view"], admin=True)
    r = client.get(
        "/api/v1/assets/cmdb/impact",
        params={"entity_type": "host", "entity_id": h1},
    )
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"root", "affected", "count"} <= set(d), (
        f"impact must return {{root, affected[], count}}; keys={sorted(d)}"
    )
    assert isinstance(d["affected"], list)


def test_b5_topology_respects_us03(p33_client):
    client, set_user, h1, _ = p33_client
    set_user(["asset:topo:view"], admin=False)  # no visible entities
    r = client.get(
        "/api/v1/assets/cmdb/topology",
        params={"entity_type": "host", "entity_id": h1, "depth": 1},
    )
    if r.status_code == 200:
        d = r.json().get("data") or {}
        assert d.get("nodes") == [], (
            "US-03: non-admin with no visible entities must see no topology nodes"
        )
    else:
        assert r.status_code == 403, r.text


def test_b6_us03_write_requires_src_and_dst_visible(p33_client):
    client, set_user, h1, h2 = p33_client
    set_user(["asset:relation:add"], admin=False)  # no visible entities
    body = {"src_type": "host", "src_id": h1, "dst_type": "host", "dst_id": h2, "rel_type": "depends_on"}
    r = client.post("/api/v1/assets/relations", json=body)
    assert r.status_code == 403, (
        f"US-03 write: POST /assets/relations must require caller-visible src AND dst (403); got {r.status_code}"
    )
    assert r.json().get("code") == 403


def test_b7_delete_first_200_then_missing_404(p33_client):
    client, set_user, h1, h2 = p33_client
    set_user(["asset:relation:list", "asset:relation:add", "asset:relation:del"], admin=True)
    body = {"src_type": "host", "src_id": h1, "dst_type": "host", "dst_id": h2, "rel_type": "depends_on"}
    assert client.post("/api/v1/assets/relations", json=body).status_code == 200

    lst = client.get("/api/v1/assets/relations")
    assert lst.status_code == 200, lst.text
    d = lst.json().get("data")
    rows = d.get("list") if isinstance(d, dict) else d
    assert rows, f"relation list must expose the created row; got {d!r}"
    rid = rows[0]["id"]

    d1 = client.delete(f"/api/v1/assets/relations/{rid}")
    assert d1.status_code == 200, (
        f"first DELETE must be 200 + Result envelope (NOT 204); got {d1.status_code}: {d1.text}"
    )
    d2 = client.delete(f"/api/v1/assets/relations/{rid}")
    assert d2.status_code == 404, (
        f"repeat/missing DELETE must be 404; got {d2.status_code}: {d2.text}"
    )


# ── B8: gate order = feature-first (P3-6 ③ unify; @架构 P3-6 tuple v1.C) ───────
# P3-3 回改 (@架构 P3-6 C): routes drop the前置 `require_perm` so the platform
# single mouth is **feature gate → permission gate** (P3-1/2/4/5 already this way):
#   no token 401 (auth layer) / flag off -> ANY authed caller 400 / flag on+no perm 403.
# Before the回改 the route-level `require_perm` ran first, so a no-perm caller with
# the flag off saw 403 — this lock pins the corrected 400.

@pytest.fixture()
def p33_client_feature_off(tmp_path):
    """Like ``p33_client`` but with `feature.cmdb_topology` DEFAULT (False) — no ConfigRule."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p33off.db'}", future=True)
    Base.metadata.create_all(engine, tables=_core_tables())
    maker = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    session = maker()

    h1_id = h2_id = None
    try:
        from app.db.models.asset import AssetGroup, Host  # noqa: PLC0415

        g = AssetGroup(parent_id=0, name="g")
        session.add(g)
        session.flush()
        h1 = Host(hostname="h1", ip="10.0.0.1", group_id=g.id)
        h2 = Host(hostname="h2", ip="10.0.0.2", group_id=g.id)
        session.add_all([h1, h2])
        session.flush()
        h1_id, h2_id = h1.id, h2.id
    except Exception:  # noqa: BLE001
        h1_id, h2_id = 1, 2
    session.commit()

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

    try:
        yield TestClient(main.app), set_user, h1_id, h2_id
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_b8_feature_gate_runs_before_permission_gate(p33_client_feature_off):
    client, set_user, _h1, _h2 = p33_client_feature_off
    # flag off (default) + admin (would pass any perm) -> 400, NOT 403
    set_user([], admin=True)
    r_admin = client.get("/api/v1/assets/relations")
    assert r_admin.status_code == 400, (
        "P3-6 ③: flag off + admin must be 400 `feature disabled` (feature gate FIRST); "
        f"got {r_admin.status_code}: {r_admin.text}"
    )
    assert r_admin.json().get("code") == 400
    # flag off + NO permission -> must still be 400 (feature BEFORE permission), NOT 403
    set_user([], admin=False)
    r_noperm = client.get("/api/v1/assets/relations")
    assert r_noperm.status_code == 400, (
        "P3-6 ③: flag off + no-perm caller must be 400, NOT 403 "
        f"(feature gate BEFORE permission gate); got {r_noperm.status_code}: {r_noperm.text}"
    )
