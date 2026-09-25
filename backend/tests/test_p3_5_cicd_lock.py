r"""P3-5 CI/CD 集成（发布编排段）contract locks — @单元测试工程师 (lock-first, add-only).

Frozen contract: @架构 **P3-5 tuple v1.0** (seq3043, base = M6 `a0131456`);
design `docs/architecture-phase23.md §14`; requirements `§27.3` (@需求 seq3041/seq3042).

Base = release **M6 = `a0131456`** (master).

Pinned surface (tuple seq3043):
  tables (add-only)  : cicd_provider / release  (+ contract `artifact_manifest`)
  migration          : +1, rev `b2c3d4e5f6a8`, parent P3-4 rev `a1b2c3d4e5f7`, single head, in C
  interfaces          : GET/POST /cicd/providers ; PUT/DELETE /cicd/providers/{id} ;
                        POST /cicd/providers/{id}/test ; POST /cicd/webhooks/{provider} (token, NOT session) ;
                        GET/POST /releases ; GET /releases/{id} ;
                        POST /releases/{id}/canary|promote|rollback|cancel|deploy|fail
  perms (14)          : cicd:provider:{list,add,edit,del,test} ; release:{list,add,view,canary,promote,rollback,cancel,deploy,fail}
  flag                : `feature.cicd` default False (feature gate FIRST)
  state machine       : release pending->deploying->canary->succeeded / failed->rolled_back /
                        terminal cancelled (deploy from pending; fail from deploying|canary;
                        cancel from pending|deploying|canary; already-terminal => 409)
  R-复用 (§14.4)      : release 编排 REUSES §13 workflow (release == 1 `workflow_run`, trigger_type=release)

EXPECTED: clean **RED** until P3-6 backend lands (add-only); import-guarded so the run
reports assertion failures rather than collection errors. Offline only (temp SQLite;
no live PG/Redis; no migrations applied).

paths note: base 144 (P3-4 收口 @ M6) + 10 URL keys == 154 (P3-5) + 2 == **156** (P3-6:
/releases/{id}/deploy·/fail; @架构 P3-6 tuple v1). `docs/openapi.json` is URL-keyed.

Run (backend checkout, backend venv):
    python -m pytest tests/test_p3_5_cicd_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib
import re

import pytest

from tests.openapi_baseline import M6_P3_4_KEYS


def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


# ── P1: permission codes (seed PERMISSION_TREE) ──────────────────────────────

CICD_PERMS = {
    "cicd:provider:list",
    "cicd:provider:add",
    "cicd:provider:edit",
    "cicd:provider:del",
    "cicd:provider:test",
    "release:list",
    "release:add",
    "release:view",
    "release:canary",
    "release:promote",
    "release:rollback",
    "release:cancel",
    "release:deploy",
    "release:fail",
}
# NOTE: count = 14 (@架构 P3-6 tuple v1). P3-5 frozen 12 (after @需求 seq3065 (A)
# deleted `release:run`, which had NO bound endpoint). P3-6 adds `release:deploy`
# / `release:fail` for the two new session endpoints (12->14 endpoints : 14 codes
# 1:1). `release:run` MUST NOT reappear.


def _perm_codes() -> set[str]:
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-5 lock: app.db.seed unavailable: {seed}")
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_cicd_permission_codes_registered():
    codes = _perm_codes()
    missing = CICD_PERMS - codes
    assert not missing, f"P3-5 permission codes missing from PERMISSION_TREE: {sorted(missing)}"


# P3-6 ② (@架构 seq3147 / @需求 seq3146/seq3148): "端点↔权限 1:1" is OPERATION-level
# (method+path), NOT URL-level. release = 9 operations ↔ 9 codes (/releases carries
# list+add ⇒ 8 URL keys); provider = 5 operations ↔ 5 codes (3 URL keys). Total 14↔14.

_RELEASE_OP_CODE = {
    ("GET", "/releases"): "release:list",
    ("POST", "/releases"): "release:add",
    ("GET", "/releases/{id}"): "release:view",
    ("POST", "/releases/{id}/canary"): "release:canary",
    ("POST", "/releases/{id}/promote"): "release:promote",
    ("POST", "/releases/{id}/rollback"): "release:rollback",
    ("POST", "/releases/{id}/cancel"): "release:cancel",
    ("POST", "/releases/{id}/deploy"): "release:deploy",
    ("POST", "/releases/{id}/fail"): "release:fail",
}
_CICD_OP_CODE = {
    ("GET", "/cicd/providers"): "cicd:provider:list",
    ("POST", "/cicd/providers"): "cicd:provider:add",
    ("PUT", "/cicd/providers/{id}"): "cicd:provider:edit",
    ("DELETE", "/cicd/providers/{id}"): "cicd:provider:del",
    ("POST", "/cicd/providers/{id}/test"): "cicd:provider:test",
}


def test_p1b_operation_code_binding_1to1_no_release_run():
    """P3-6 ②: 14 operations ↔ 14 permission codes, 1:1; `release:run` must NOT exist."""
    codes = _perm_codes()
    op_codes = set(_RELEASE_OP_CODE.values()) | set(_CICD_OP_CODE.values())
    assert len(_RELEASE_OP_CODE) == 9 and len(_CICD_OP_CODE) == 5
    assert len(op_codes) == 14, f"expected 14 distinct operation codes; got {len(op_codes)}"
    assert op_codes == set(CICD_PERMS), "operation→code map must equal the CICD_PERMS set"
    missing = op_codes - codes
    assert not missing, f"P3-6 operation codes not seeded: {sorted(missing)}"
    assert "release:run" not in codes, "`release:run` must NOT be seeded (no such operation)"
    assert "release:run" not in CICD_PERMS


def test_p1c_seed_menu_button_counts():
    """P3-6 ② counting lock (@架构 seq3147): +2 release buttons; menus unchanged (26)."""
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-6 lock: app.db.seed unavailable: {seed}")
    tree = getattr(seed, "PERMISSION_TREE", [])
    menus = [node[0] for node in tree]
    buttons = [child[0] for node in tree for child in node[5]]
    assert len(menus) == 26, f"menus must stay 26 (no new menu); got {len(menus)}"
    assert len(buttons) == 110, (
        f"buttons must be 110 (108 + release:deploy/fail); got {len(buttons)}"
    )


# ── A1/A2: openapi runtime surface ───────────────────────────────────────────

_CICD = r"/api/v1/cicd"
_REL = r"/api/v1/releases"


def _cicd_paths() -> dict[str, set[str]]:
    return {
        _CICD + r"/providers": {"get", "post"},
        _CICD + r"/providers/\{[^}]+\}": {"put", "delete"},
        _CICD + r"/providers/\{[^}]+\}/test": {"post"},
        _CICD + r"/webhooks/\{[^}]+\}": {"post"},
        _REL: {"get", "post"},
        _REL + r"/\{[^}]+\}": {"get"},
        _REL + r"/\{[^}]+\}/canary": {"post"},
        _REL + r"/\{[^}]+\}/promote": {"post"},
        _REL + r"/\{[^}]+\}/rollback": {"post"},
        _REL + r"/\{[^}]+\}/cancel": {"post"},
        _REL + r"/\{[^}]+\}/deploy": {"post"},
        _REL + r"/\{[^}]+\}/fail": {"post"},
    }


_METHODS = {"get", "post", "put", "delete", "patch"}


def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-5 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p3_5_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for pat, want in _cicd_paths().items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in _METHODS}
        miss = want - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P3-5 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_at_least_156():
    paths = _openapi_paths()
    # P3-6 收尾批 anchored EXACTLY 156 (@架构 P3-6 tuple v1). P4 (AIOps) is
    # add-only on top; the P3-5/P3-6 floor is now a MONOTONIC no-shrink check
    # (>=156) with the exact count pinned at the newest batch lock
    # (test_p4_aiops_lock::test_a2_paths_count_164 + test_contract_openapi==164).
    # Must NOT shrink below 156.
    assert len(paths) >= 156, (
        f"paths must be >= 156 (P3-6 floor: P3-5 154 + 2 deploy/fail URL keys); got {len(paths)}. "
        "OpenAPI `paths` is URL-keyed."
    )
    # layer ④ (@架构 seq3057): no-shrink against the FROZEN M6 baseline key set — a
    # net-zero substitution (drop 1 old key, add 1 extra new key, still ==154) would
    # otherwise pass the exact-count + per-key layers.
    removed = set(M6_P3_4_KEYS) - set(paths)
    assert not removed, (
        f"openapi keys must not shrink below the M6 baseline (layer ④, @架构 seq3057): "
        f"removed={sorted(removed)}"
    )


# ── M1/M2: SQLAlchemy tables & core columns ──────────────────────────────────

CICD_TABLES = ("cicd_provider", "release")
PROVIDER_COLS = {
    "id", "type", "name", "endpoint", "config_enc", "enabled", "status",
    "last_heartbeat", "created_by", "created_at", "updated_at",
}
RELEASE_COLS = {
    "id", "provider_id", "app", "env", "status", "workflow_run_id",
    "target_host_ids", "rolled_back_from", "created_by", "created_at", "updated_at",
}


def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415  (register all models)
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P3-5 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_cicd_tables_registered():
    tables = _tables()
    missing = [t for t in CICD_TABLES if t not in tables]
    assert not missing, f"P3-5 must define {list(CICD_TABLES)} (§14.2); missing {missing}"


def test_m2_cicd_core_columns():
    tables = _tables()
    problems = []
    for name, want in (("cicd_provider", PROVIDER_COLS), ("release", RELEASE_COLS)):
        t = tables.get(name)
        if t is None:
            problems.append(f"{name}: table missing")
            continue
        miss = want - set(t.columns.keys())
        if miss:
            problems.append(f"{name}: missing columns {sorted(miss)}")
    r = tables.get("release")
    if r is not None:
        cols = set(r.columns.keys())
        if not ({"version", "artifact_ref"} & cols):
            problems.append("release: must carry `version` or `artifact_ref` (§14.2)")
    assert not problems, "P3-5 column contract: " + "; ".join(problems)


# ── F1: feature flag default off ─────────────────────────────────────────────

def test_f1_feature_cicd_default_false():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P3-5 lock: app.db.seed unavailable: {seed}")
    entry = getattr(seed, "DEFAULT_CONFIG_RULES", {}).get("feature.cicd")
    assert entry is not None, "feature.cicd not seeded in DEFAULT_CONFIG_RULES"
    assert entry.get("value") is False, (
        f"feature.cicd default must be False; got {entry.get('value')!r}"
    )


# ── G1: migration single head descending from the P3-4 rev ───────────────────

_VERSIONS_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "alembic" / "versions"
_P34_HEAD = "a1b2c3d4e5f7"
_P35_REV = "b2c3d4e5f6a8"
# 形近陷阱: `b2c3d4e5f6a7` is the EXISTING P2-1 transfer-table rev (docs §14.3) — must NOT be reused.
_P21_TRANSFER_REV = "b2c3d4e5f6a7"


def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    return revs


def test_g1_migration_single_head_descends_from_p34():
    revs = _revision_graph()
    assert _P34_HEAD in revs, f"P3-4 head {_P34_HEAD} missing from versions dir"
    assert _P21_TRANSFER_REV in revs, f"existing P2-1 rev {_P21_TRANSFER_REV} expected (sanity)"
    assert _P35_REV != _P21_TRANSFER_REV, "P3-5 rev must not collide with P2-1 transfer rev"
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    head = heads[0]
    assert head == _P35_REV, (
        f"P3-5 head must be the suggested rev `{_P35_REV}`; got {head}"
    )
    assert revs[head] == _P34_HEAD, (
        f"P3-5 head must descend directly from P3-4 rev {_P34_HEAD}; got parent {revs[head]!r}"
    )


def test_g2_forbidden_set_includes_p35_rev_and_is_disjoint():
    """Naming-collision guard (@架构 seq3053 item 2).

    The P3-5 rev must enter C via the NAMED symbol `P3_5_REV` (no inline literal),
    C ∩ B must stay empty, and the look-alike rev `b2c3d4e5f6a7` must belong to B.
    """
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    p = Path(__file__).resolve().parent / "test_live_env_contract_lock.py"
    spec = importlib.util.spec_from_file_location("_p35_live_contract_lock", p)
    if spec is None or spec.loader is None:
        pytest.fail("P3-5 lock: cannot load test_live_env_contract_lock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert getattr(mod, "P3_5_REV", None) == _P35_REV, (
        "test_live_env_contract_lock.py must expose the named symbol "
        f"P3_5_REV == {_P35_REV!r} (C must reference it, not an inline literal)"
    )
    assert _P35_REV in mod.MIGRATION_LIVE_FORBIDDEN, f"{_P35_REV} must be a member of C"
    assert mod.MIGRATION_LIVE_APPLICABLE & mod.MIGRATION_LIVE_FORBIDDEN == set(), (
        "B ∩ C must stay empty (a migration cannot be both applicable and forbidden)"
    )
    assert _P21_TRANSFER_REV in mod.MIGRATION_LIVE_APPLICABLE, (
        f"the look-alike rev {_P21_TRANSFER_REV} belongs to B (applicable), NOT C"
    )


# ── R0–R8: route-level behavioural locks (offline TestClient) ────────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

_WF_TABLES = ("workflow", "workflow_version", "workflow_run", "workflow_node_run")
_CORE_TABLES = (
    "config_rule", "sys_audit_log", "sys_user", "exec_task", "exec_task_host",
    "approval_request", "approval_rule", "approval_record",
    *CICD_TABLES, *_WF_TABLES,
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


_ACTION_PERMS = [
    "cicd:provider:add",
    "release:add",
    "release:view",
    "release:canary",
    "release:promote",
    "release:rollback",
    "release:deploy",
    "release:fail",
]


def _seed_release(client, *, app, env="dev"):
    """Create a provider + a `pending` release through the API; return the release id."""
    prov = client.post(
        "/api/v1/cicd/providers",
        json={"type": "generic", "name": f"g-{app}", "endpoint": "https://g"},
    )
    assert prov.status_code == 200, prov.text
    pid = (prov.json().get("data") or {}).get("id")
    rel = client.post(
        "/api/v1/releases",
        json={"provider_id": pid, "app": app, "version": "1.0.0", "env": env},
    )
    assert rel.status_code == 200, rel.text
    return (rel.json().get("data") or {}).get("id")


@pytest.fixture()
def cicd_client(tmp_path):
    """Yields ``(client, set_user, set_flag)``."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p35.db'}", future=True)
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

            row = session.query(ConfigRule).filter_by(rule_key="feature.cicd").one_or_none()
            if row is None:
                session.add(ConfigRule(rule_key="feature.cicd", rule_value={"value": on}))
            else:
                row.rule_value = {"value": on}
            session.commit()
        except Exception:  # noqa: BLE001
            pass

    try:
        yield TestClient(main.app), set_user, set_flag, session
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


def test_r0_feature_gate_runs_first_400_for_any_caller(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(False)
    # admin (would pass any perm gate) still gets 400 because the FEATURE gate is first
    set_user([], admin=True)
    for path in ("/api/v1/cicd/providers", "/api/v1/releases"):
        r = client.get(path)
        assert r.status_code == 400, (
            f"flag off + admin must be 400 `feature disabled` (feature gate FIRST) on {path}; "
            f"got {r.status_code}: {r.text}"
        )
        assert r.json().get("code") == 400
    # no-perm caller also gets 400 (NOT 403) — proves feature-before-permission order
    set_user([], admin=False)
    r2 = client.get("/api/v1/cicd/providers")
    assert r2.status_code == 400, (
        f"flag off + no-perm caller must be 400, NOT 403 (feature gate FIRST); "
        f"got {r2.status_code}: {r2.text}"
    )


def test_r1_flag_on_missing_perm_403(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user([], admin=False)
    r = client.get("/api/v1/cicd/providers")
    assert r.status_code == 403, (
        f"flag on + missing cicd:provider:list must be 403; got {r.status_code}: {r.text}"
    )


def test_r2_provider_create_and_invalid_type_422(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(["cicd:provider:add", "cicd:provider:list"], admin=True)
    r = client.post(
        "/api/v1/cicd/providers",
        json={"type": "gitlab", "name": "gl", "endpoint": "https://gitlab.example.com"},
    )
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"id", "type", "name"} <= set(d), (
        f"created provider must expose id/type/name; keys={sorted(d)}"
    )
    bad = client.post(
        "/api/v1/cicd/providers",
        json={"type": "bogus", "name": "x", "endpoint": "https://x"},
    )
    assert bad.status_code == 422, (
        f"provider type must be ∈ {{gitlab,jenkins,generic}}, bad type -> 422; "
        f"got {bad.status_code}: {bad.text}"
    )


def test_r3_provider_list_page(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(["cicd:provider:list"], admin=True)
    r = client.get("/api/v1/cicd/providers")
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"list", "total", "page", "size"} <= set(d), (
        f"GET /cicd/providers must return Page {{list,total,page,size}}; keys={sorted(d)}"
    )
    assert isinstance(d["list"], list)


def test_r4_provider_secret_not_echoed_plaintext(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(["cicd:provider:add", "cicd:provider:list"], admin=True)
    secret = "s3cr3t-token-XYZ"
    r = client.post(
        "/api/v1/cicd/providers",
        json={
            "type": "jenkins", "name": "jk", "endpoint": "https://jk.example.com",
            "config": {"token": secret},
        },
    )
    assert r.status_code == 200, r.text
    pid = (r.json().get("data") or {}).get("id")
    fresh = client.get("/api/v1/cicd/providers")
    assert fresh.status_code == 200, fresh.text
    assert secret not in fresh.text, (
        "§14.2: provider config_enc 密钥逐值密文; the plaintext secret must NOT be echoed"
    )
    assert pid is not None


def test_r5_releases_create_and_invalid_env_422(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(
        ["cicd:provider:add", "release:add", "release:view", "release:list"], admin=True
    )
    prov = client.post(
        "/api/v1/cicd/providers",
        json={"type": "generic", "name": "g", "endpoint": "https://g"},
    )
    assert prov.status_code == 200, prov.text
    pid = (prov.json().get("data") or {}).get("id")
    r = client.post(
        "/api/v1/releases",
        json={"provider_id": pid, "app": "svc-a", "version": "1.0.0", "env": "dev"},
    )
    assert r.status_code == 200, r.text
    d = r.json().get("data") or {}
    assert {"id", "status"} <= set(d), f"created release must expose id/status; keys={sorted(d)}"
    assert d["status"] == "pending", (
        f"new release status must be `pending` (§14.1 state machine); got {d['status']!r}"
    )
    bad = client.post(
        "/api/v1/releases",
        json={"provider_id": pid, "app": "svc-a", "version": "1.0.0", "env": "bogus"},
    )
    assert bad.status_code == 422, (
        f"release env must be ∈ {{dev,test,prod}}, bad env -> 422; got {bad.status_code}: {bad.text}"
    )


def test_r6_release_cancel_from_pending_then_terminal_409(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(
        ["cicd:provider:add", "release:add", "release:view", "release:cancel"], admin=True
    )
    prov = client.post(
        "/api/v1/cicd/providers",
        json={"type": "generic", "name": "g2", "endpoint": "https://g"},
    )
    assert prov.status_code == 200, prov.text
    pid = (prov.json().get("data") or {}).get("id")
    created = client.post(
        "/api/v1/releases",
        json={"provider_id": pid, "app": "svc-b", "version": "1.0.0", "env": "test"},
    )
    assert created.status_code == 200, created.text
    rid = (created.json().get("data") or {}).get("id")
    c1 = client.post(f"/api/v1/releases/{rid}/cancel")
    assert c1.status_code == 200, (
        f"cancel from `pending` must be allowed (§14.1); got {c1.status_code}: {c1.text}"
    )
    c2 = client.post(f"/api/v1/releases/{rid}/cancel")
    assert c2.status_code == 409, (
        f"cancel on an already-terminal release must be 409 (§14.1); got {c2.status_code}: {c2.text}"
    )


def test_r7_webhook_token_gate_not_session_401(cicd_client):
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user([], admin=False)
    # inbound webhook uses a provider token, NOT a session/perm: no credentials -> 401
    r = client.post("/api/v1/cicd/webhooks/gitlab", json={})
    assert r.status_code == 401, (
        f"POST /cicd/webhooks/{{provider}} is provider-token guarded (NOT session/perm); "
        f"missing token must be 401; got {r.status_code}: {r.text}"
    )


def test_r8_release_reuses_section13_workflow_run(cicd_client):
    """§14.4: a release IS one §13 `workflow_run` (trigger_type="release").

    Implementation-neutral proof of R-复用: once a release is triggered, a REAL
    `workflow_run` row linked to the release must exist (no re-implementation of
    the orchestrator).
    """
    client, set_user, set_flag, session = cicd_client
    set_flag(True)
    set_user(
        ["cicd:provider:add", "release:add", "release:view", "release:canary"],
        admin=True,
    )
    prov = client.post(
        "/api/v1/cicd/providers",
        json={"type": "generic", "name": "g3", "endpoint": "https://g"},
    )
    assert prov.status_code == 200, prov.text
    pid = (prov.json().get("data") or {}).get("id")
    created = client.post(
        "/api/v1/releases",
        json={"provider_id": pid, "app": "svc-c", "version": "1.0.0", "env": "dev"},
    )
    assert created.status_code == 200, created.text
    rid = (created.json().get("data") or {}).get("id")
    client.post(f"/api/v1/releases/{rid}/canary")

    from sqlalchemy import text  # noqa: PLC0415

    rows = session.execute(
        text("SELECT COUNT(*) FROM workflow_run WHERE trigger_type = 'release'")
    ).scalar()
    assert rows and rows >= 1, (
        "§14.4: triggering a release must create a REAL §13 workflow_run "
        "(trigger_type='release'); none found — release must NOT re-implement the orchestrator"
    )


def test_r9_action_gate_canary_from_canary_409(cicd_client):
    """§14.1 state machine: canary source ∈ {pending, deploying}; from `canary` -> 409."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-g")
    first = client.post(f"/api/v1/releases/{rid}/canary")
    assert first.status_code == 200, (
        f"canary from `pending` must be allowed (§14.1); got {first.status_code}: {first.text}"
    )
    again = client.post(f"/api/v1/releases/{rid}/canary")
    assert again.status_code == 409, (
        f"canary from `canary` must be 409 (illegal source state, §14.1); "
        f"got {again.status_code}: {again.text}"
    )


def test_r10_action_gate_promote_from_pending_409(cicd_client):
    """§14.1 state machine: promote source = `canary` only; from `pending` -> 409."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-h")
    r = client.post(f"/api/v1/releases/{rid}/promote")
    assert r.status_code == 409, (
        f"promote from `pending` must be 409 (promote source = `canary`, §14.1); "
        f"got {r.status_code}: {r.text}"
    )


def test_r11_action_gate_rollback_from_succeeded_409(cicd_client):
    """§27.3 ③ state machine (amended @架构 seq3077): rollback source = {deploying, canary, failed}; from terminal `succeeded` -> 409."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-i")
    can = client.post(f"/api/v1/releases/{rid}/canary")
    assert can.status_code == 200, can.text
    prom = client.post(f"/api/v1/releases/{rid}/promote")
    assert prom.status_code == 200, (
        f"promote from `canary` must succeed (§14.1 `canary→succeeded`); "
        f"got {prom.status_code}: {prom.text}"
    )
    rb = client.post(f"/api/v1/releases/{rid}/rollback")
    assert rb.status_code == 409, (
        f"rollback from terminal `succeeded` must be 409 "
        f"(rollback source = {{deploying,canary,failed}}, §27.3 ③); "
        f"got {rb.status_code}: {rb.text}"
    )


def test_r12_release_transitions_exact_source_sets():
    """§14.1 state machine (@架构 P3-6 tuple v1): pin RELEASE_TRANSITIONS action->source sets.

    Constant-level assertion (no DB). `deploy`/`fail` are no longer reserved: P3-6
    adds their routes, so all SIX actions are pinned exactly.
    """
    mod = _try("app.services.cicd_service")
    if isinstance(mod, Exception):
        pytest.fail(f"P3-5 lock: app.services.cicd_service unavailable: {mod}")
    t = getattr(mod, "RELEASE_TRANSITIONS", None)
    assert isinstance(t, dict), "app.services.cicd_service.RELEASE_TRANSITIONS missing (§14.1)"
    expected = {
        "deploy": (("pending",), "deploying"),
        "canary": (("pending", "deploying"), "canary"),
        "promote": (("canary",), "succeeded"),
        "fail": (("deploying", "canary"), "failed"),
        "rollback": (("deploying", "canary", "failed"), "rolled_back"),
        "cancel": (("pending", "deploying", "canary"), "cancelled"),
    }
    for action, exp in expected.items():
        assert action in t, f"RELEASE_TRANSITIONS missing action {action!r} (§14.1)"
        assert t[action] == exp, (
            f"RELEASE_TRANSITIONS[{action!r}] must be exactly {exp!r} "
            f"(§14.1 / @架构 P3-6 tuple v1); got {t[action]!r}"
        )


def test_r13_rollback_from_canary_200_rolled_back(cicd_client):
    """§27.3 ③ (@架构 seq3077 amend): `canary` ∈ rollback source ⇒ 200 `rolled_back`."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-j")
    can = client.post(f"/api/v1/releases/{rid}/canary")
    assert can.status_code == 200, can.text
    rb = client.post(f"/api/v1/releases/{rid}/rollback")
    assert rb.status_code == 200, (
        f"rollback from `canary` must be allowed (source set includes canary; "
        f"§27.3 ③ @架构 seq3077); got {rb.status_code}: {rb.text}"
    )
    st = (rb.json().get("data") or {}).get("status")
    assert st == "rolled_back", f"rollback target must be `rolled_back`; got {st!r}"


# ── R14–R19: P3-6 `deploy`/`fail` action endpoints (@架构 P3-6 tuple v1) ───────


def test_r14_deploy_from_pending_200_deploying(cicd_client):
    """P3-6: `POST /releases/{id}/deploy` makes `deploying` reachable (source `pending`)."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-k")
    r = client.post(f"/api/v1/releases/{rid}/deploy")
    assert r.status_code == 200, (
        f"deploy from `pending` must be allowed (source set = {{pending}}); got "
        f"{r.status_code}: {r.text}"
    )
    st = (r.json().get("data") or {}).get("status")
    assert st == "deploying", f"deploy target must be `deploying`; got {st!r}"


def test_r15_deploy_from_canary_409(cicd_client):
    """deploy source = `pending` only; from `canary` -> 409."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-l")
    assert client.post(f"/api/v1/releases/{rid}/canary").status_code == 200
    r = client.post(f"/api/v1/releases/{rid}/deploy")
    assert r.status_code == 409, (
        f"deploy from `canary` must be 409 (deploy source = {{pending}}); "
        f"got {r.status_code}: {r.text}"
    )


def test_r16_fail_from_canary_200_failed(cicd_client):
    """`POST /releases/{id}/fail` makes `failed` reachable (source `deploying|canary`)."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-m")
    assert client.post(f"/api/v1/releases/{rid}/canary").status_code == 200
    r = client.post(f"/api/v1/releases/{rid}/fail")
    assert r.status_code == 200, (
        f"fail from `canary` must be allowed (source set = {{deploying,canary}}); got "
        f"{r.status_code}: {r.text}"
    )
    st = (r.json().get("data") or {}).get("status")
    assert st == "failed", f"fail target must be `failed`; got {st!r}"


def test_r17_fail_from_pending_409(cicd_client):
    """fail source = {deploying, canary}; from `pending` -> 409."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-n")
    r = client.post(f"/api/v1/releases/{rid}/fail")
    assert r.status_code == 409, (
        f"fail from `pending` must be 409 (fail source = {{deploying,canary}}); "
        f"got {r.status_code}: {r.text}"
    )


def test_r18_deploy_requires_release_deploy_perm_403(cicd_client):
    """New endpoint binds `release:deploy` (endpoint↔perm 1:1); missing perm -> 403."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-o")
    set_user(["release:view"], admin=False)  # flag on, but no release:deploy
    r = client.post(f"/api/v1/releases/{rid}/deploy")
    assert r.status_code == 403, (
        f"deploy with flag on but no `release:deploy` must be 403; got {r.status_code}: {r.text}"
    )


def test_r19_feature_gate_before_perm_on_deploy_fail(cicd_client):
    """Feature gate FIRST also holds for the new deploy/fail routes (flag off + admin -> 400)."""
    client, set_user, set_flag, _ = cicd_client
    set_flag(True)
    set_user(_ACTION_PERMS, admin=True)
    rid = _seed_release(client, app="svc-p")
    set_flag(False)
    set_user([], admin=True)
    for path in (f"/api/v1/releases/{rid}/deploy", f"/api/v1/releases/{rid}/fail"):
        r = client.post(path)
        assert r.status_code == 400, (
            f"flag off + admin must be 400 `feature disabled` (feature gate FIRST) on {path}; "
            f"got {r.status_code}: {r.text}"
        )
