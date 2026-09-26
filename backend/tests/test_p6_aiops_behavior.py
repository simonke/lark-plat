r"""P6 (AIOps E6) behaviour tests — @单元 lock-first behaviour RED (non-lock).

Companion to `test_p6_aiops_lock.py` (contract-surface lock, blob frozen). This
file pins the **behavioural semantics** the structural lock cannot grep, per
@架构 `3602`/`3606`⑤ and `3611` (seam = shared core `create_exec_task_record`) +
@reviewer `3612` (the `retry_task` site must also be covered).

Frozen contract: @架构 P6 tuple r1 (seq3560 + notes r1.1-r1.8) + @需求 §30.
Base = branch `p6-aiops`; behaviour RED against tip `5f7e77cb` (green superseded
by the behaviour fixes this file will force).

Groups:
  ① put_level r1.8 four assertions — currently GREEN (regression floor).
  ② E6-3 positive: an auto_policy decision writes exactly one pre-authorised
     `ApprovalRequest(approval_mode='auto_policy', status='approved')` + exactly
     one `ai_action(decision='auto')`; construction sites stay == 6.
  ③ E6-3 negative: outside whitelist / risk=high / current!=L4 => stays
     `manual`/`pending`, zero `ai_action(decision='auto')` (non-vacuous).
  ④ E6-4 rollback: first rollback => Δexec_task==+1 AND Δapproval_request==+1 AND
     rollback_ref set; repeat rollback => Δ0.

Offline only (no live PG/Redis; no migrations). sqlite shim registers a
`nextval(name)` UDF because `_task_no`/`_approval_no` call PG sequences.

Run (backend checkout, backend venv):
    python -m pytest tests/test_p6_aiops_behavior.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


def _require(mod: str):
    obj = _try(mod)
    if isinstance(obj, Exception):
        pytest.fail(f"P6 behaviour: `{mod}` unavailable: {obj!r}")
    return obj


def _data(response) -> dict:
    """Unwrap the `{"code":0,"message":"ok","data":...}` envelope."""
    body = response.json()
    assert body.get("code") == 0, f"unexpected envelope: {body!r}"
    return body["data"]


# ── offline harness (sqlite; PG-only bits shimmed) ───────────────────────────

import app.db.session as _dbs  # noqa: E402
from sqlalchemy import BigInteger, create_engine, event  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    return "INTEGER"


_P6_TABLES = (
    "config_rule",
    "sys_user",
    "automation_level",
    "automation_whitelist",
    "remediation_policy",
    "circuit_breaker_state",
    "approval_request",
    "approval_record",
    "ai_action",
    "exec_task",
    "exec_task_host",
    "host",
    "workflow_run",
    "workflow_node_run",
)


def _mk_tables():
    import app.db.models  # noqa: F401,PLC0415
    from app.db.base import Base  # noqa: PLC0415

    tl = Base.metadata.tables
    return [tl[n] for n in _P6_TABLES if n in tl]


def _install_nextval(engine) -> None:
    """sqlite lacks PG sequences; `_task_no`/`_approval_no` call
    `SELECT nextval('seq_...')`. Back it with a monotonic counter (per name)."""

    counters: dict[str, int] = {}

    def _nextval(name: str) -> int:
        counters[name] = counters.get(name, 0) + 1
        return counters[name]

    @event.listens_for(engine, "connect")
    def _register(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.create_function("nextval", 1, _nextval)


class _User:
    """Minimal stand-in for CurrentUser used by service-layer calls."""

    def __init__(self, perms, admin=True):
        self.id = 1
        self.user_id = 1
        self.username = "qa"
        self.is_admin = admin
        self.permissions = list(perms)
        self.visible_group_ids = []

    def require_perm(self, perm: str) -> None:
        from app.core.exceptions import ForbiddenError

        if perm not in self.permissions:
            raise ForbiddenError(f"missing permission {perm}")


@pytest.fixture()
def p6_db(tmp_path):
    """Yields ``(session, set_user, set_flag, client)`` for behaviour tests.

    ``set_user``/``set_flag`` drive the HTTP client (gate/permission); ``session``
    is the same sqlite session the app uses (dependency override) so tests can
    assert on DB rows directly.
    """
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p6b.db'}", future=True)
    _install_nextval(engine)
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
        yield session, set_user, set_flag, TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()
        session.close()
        if prev_bind is not None:
            _dbs.SessionLocal.configure(bind=prev_bind)
        engine.dispose()


# ── ① put_level r1.8 (frozen; currently GREEN) ───────────────────────────────

def _enabled_levels(session) -> list[str]:
    from app.db.models import AutomationLevel  # noqa: PLC0415

    rows = session.query(AutomationLevel).all()
    return sorted(r.level for r in rows if r.enabled)


def test_b1_put_level_r1_8_mutual_exclusion(p6_db):
    """FR-E6-1 r1.8: single `current`, PUT mutual exclusion, default L3, same-value no-op."""
    _session, set_user, set_flag, client = p6_db
    set_flag("ai.auto_remediate", True)
    set_user(["ai:use", "ai:admin"], admin=True)

    body = client.get("/api/v1/ai/automation/level")
    assert body.status_code == 200, body.text
    assert _data(body)["current"] == "L3", "empty matrix => default current L3"

    r = client.put("/api/v1/ai/automation/level", json={"current": "L4"})
    assert r.status_code == 200, r.text
    got = _data(r)
    assert got["current"] == "L4"
    assert next(m for m in got["matrix"] if m["level"] == "L4")["enabled"]
    assert _enabled_levels(p6_db[0]) == ["L4"], "PUT L4 => exactly one enabled level"

    r = client.put("/api/v1/ai/automation/level", json={"current": "L2"})
    assert r.status_code == 200, r.text
    assert _data(r)["current"] == "L2", "PUT L2 => current L2 (two-way symmetric, old bug)"
    assert _enabled_levels(p6_db[0]) == ["L2"], "L4 must be disabled after PUT L2"

    r = client.put("/api/v1/ai/automation/level", json={"current": "L2"})
    assert r.status_code == 200, r.text
    assert _data(r)["current"] == "L2"
    assert _enabled_levels(p6_db[0]) == ["L2"], "same-value PUT is a no-op"
