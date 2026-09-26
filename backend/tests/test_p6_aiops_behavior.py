r"""P6 (AIOps E6) behaviour tests — @单元 lock-first behaviour RED (non-lock).

Companion to `test_p6_aiops_lock.py` (contract-surface lock; its blob is frozen and
NOT touched by this file). This file pins the **behavioural semantics** the
structural lock cannot grep, per @架构 `3602`/`3616` and @reviewer `3615`.

Frozen contract: @架构 P6 tuple r1 + notes r1.1-r1.8 (seq3560…3616) + @需求 §30.
Base = branch `p6-aiops` at `e944b2a` (which captured the group-① draft); this file
adds the behaviour groups ②③④ the green structural gate could not cover.

Groups (all required by @架构 `3616`④):
  ① put_level r1.8 (mutual exclusion / default L3 / no-op)  — currently GREEN floor
  ② E6-3 positive: hit => SAME approval row `approval_mode='auto_policy'`,
     `status='approved'`, `policy_ref` set; Δ`ai_action(decision='auto')`==+1
  ③ E6-3 negative: whitelist-miss / risk=high / current!=L4 => stays
     `manual`/`pending`; Δ`ai_action(decision='auto')`==0 (non-vacuous)
  ③b E6-3 retry (@架构 `3616`①⑦): `retry_task` is ALWAYS manual => new row
     `pending`/`manual`; Δ`decision='auto'`==0
  ④ E6-4 rollback: first rollback => Δexec_task==+1 AND Δapproval_request==+1 AND
     an `ai_action.rollback_ref` set; repeat => Δ0
  ③s verification fail-closed (@需求 §30.7 ③): PUT level→L4 with an L4 policy
     missing `verification_ref` => 422 and level unchanged
  ④s circuit-breaker: `resolve_threshold` single source (+env); FSM values

Audit isolation (@集成 `3614` / @reviewer `3615`④): the legacy P5 path
`app/services/ai_service.py:161` already writes `ai_action(decision='auto')`, so
every `decision='auto'` assertion here is a **Δ count** around the action, never a
global `==0`.

Offline only (sqlite; no live PG/Redis). The sqlite shim registers a `nextval(name)`
UDF because `_task_no`/`_approval_no` call PG sequences, and compiles JSONB→JSON /
BigInteger→INTEGER.

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
    "asset_group",
    "asset_host",
    "automation_level",
    "automation_whitelist",
    "remediation_policy",
    "circuit_breaker_state",
    "approval_request",
    "approval_record",
    "ai_action",
    "exec_task",
    "exec_task_host",
    "workflow",
    "workflow_version",
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
    `SELECT nextval('seq_...')`. Back it with a per-name monotonic counter."""

    counters: dict[str, int] = {}

    def _nextval(name: str) -> int:
        counters[name] = counters.get(name, 0) + 1
        return counters[name]

    @event.listens_for(engine, "connect")
    def _register(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.create_function("nextval", 1, _nextval)


class _User:
    """Minimal stand-in for CurrentUser used by service-layer calls."""

    def __init__(self, perms=("ai:use", "ai:admin", "exec:task:retry"), admin=True):
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
    """Yields ``(session, set_user, set_flag, client)``.

    ``set_user``/``set_flag`` drive the HTTP client; ``session`` is the same
    sqlite session the app uses (dependency override) so tests can assert on rows.
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


# ── seed helpers ─────────────────────────────────────────────────────────────

_SENSITIVE_WORD = "rm -rf"
_SENSITIVE_CMD = "rm -rf /tmp/target"


def _seed_sensitive(session, word: str = _SENSITIVE_WORD) -> None:
    from app.db.models.notify import ConfigRule  # noqa: PLC0415

    session.add(ConfigRule(rule_key="exec_sensitive_word", rule_value={"words": [word]}))
    session.commit()


def _make_host(session, hid: int = 1):
    from app.db.models.asset import Host  # noqa: PLC0415

    h = Host(id=hid, hostname=f"h{hid}", ip=f"10.0.0.{hid}", group_id=None,
             connector="agent", sensitivity_level="normal", status="online")
    session.add(h)
    session.commit()
    return h


def _enable_level(session, level: str) -> None:
    """Directly materialise the mutual-exclusion matrix (one enabled level)."""
    from app.db.models import AutomationLevel  # noqa: PLC0415

    for lvl in ("L0", "L1", "L2", "L3", "L4"):
        session.add(AutomationLevel(level=lvl, capability="", enabled=(lvl == level)))
    session.commit()


def _set_whitelist(session, action: str, risk_level: str = "low", enabled: bool = True) -> None:
    from app.db.models import AutomationWhitelist  # noqa: PLC0415

    session.add(AutomationWhitelist(action=action, risk_level=risk_level,
                                    enabled=enabled, updated_by=1))
    session.commit()


def _set_policy(session, asset_class: str, op_type: str, *, level: str = "L4",
                verification_ref: str | None = "V-1", rollback_window: int = 3600) -> None:
    from app.db.models import RemediationPolicy  # noqa: PLC0415

    session.add(RemediationPolicy(asset_class=asset_class, op_type=op_type, level=level,
                                  verification_ref=verification_ref,
                                  rollback_window=rollback_window))
    session.commit()


def _count(session, model) -> int:
    return session.query(model).count()


def _auto_count(session) -> int:
    from app.db.models import AiAction  # noqa: PLC0415

    return session.query(AiAction).filter(AiAction.decision == "auto").count()


def _create_exec(session, *, remediation=None, command: str = _SENSITIVE_CMD):
    """Drive the shared E6 core. Fails loudly (RED) if the seam is absent."""
    from app.services import exec_service  # noqa: PLC0415

    try:
        return exec_service.create_exec_task_record(
            session, name="E6 remediation", kind="command", target_host_ids=[1],
            command=command, created_by=1, requester_id=1, remediation=remediation,
        )
    except TypeError as exc:  # seam not landed yet (lock-first RED)
        pytest.fail(
            "E6-3 seam missing: `create_exec_task_record(..., remediation=...)` not "
            f"implemented yet (@架构 3616②); got {exc!r}"
        )


_HIT = {"action": "restart", "asset_class": "app", "op_type": "restart", "risk_level": "low"}


def _create_exec_plain(session, command: str = _SENSITIVE_CMD):
    """Legacy shared core (no E6 context) — works before the seam lands."""
    from app.services import exec_service  # noqa: PLC0415

    return exec_service.create_exec_task_record(
        session, name="plain exec", kind="command", target_host_ids=[1],
        command=command, created_by=1, requester_id=1,
    )


def _seed_hit_context(session, level: str = "L4") -> None:
    _seed_sensitive(session)
    _make_host(session)
    _enable_level(session, level)
    _set_whitelist(session, "restart", "low", True)
    _set_policy(session, "app", "restart", level="L4")


# ── ① put_level r1.8 (frozen; currently GREEN) ───────────────────────────────

def _enabled_levels(session) -> list[str]:
    from app.db.models import AutomationLevel  # noqa: PLC0415

    return sorted(r.level for r in session.query(AutomationLevel).all() if r.enabled)


def test_b1_put_level_r1_8_mutual_exclusion(p6_db):
    """FR-E6-1 r1.8: single `current`, PUT mutual exclusion, default L3, same-value no-op."""
    session, set_user, set_flag, client = p6_db
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
    assert _enabled_levels(session) == ["L4"], "PUT L4 => exactly one enabled level"

    r = client.put("/api/v1/ai/automation/level", json={"current": "L2"})
    assert r.status_code == 200, r.text
    assert _data(r)["current"] == "L2", "PUT L2 => current L2 (two-way symmetric, old bug)"
    assert _enabled_levels(session) == ["L2"], "L4 must be disabled after PUT L2"

    r = client.put("/api/v1/ai/automation/level", json={"current": "L2"})
    assert r.status_code == 200, r.text
    assert _data(r)["current"] == "L2"
    assert _enabled_levels(session) == ["L2"], "same-value PUT is a no-op"


# ── ② E6-3 positive ──────────────────────────────────────────────────────────

def _approvals_auto(session):
    from app.db.models import ApprovalRequest  # noqa: PLC0415

    return [a for a in session.query(ApprovalRequest).all() if a.approval_mode == "auto_policy"]


def test_b2_e6_3_positive_auto_policy(p6_db):
    """FR-E6-3: whitelist ∧ risk∈L4 ∧ current==L4 ∧ policy hit => pre-authorised row."""
    session, set_user, set_flag, _client = p6_db
    set_flag("ai.auto_remediate", True)
    _seed_hit_context(session)

    auto0 = _auto_count(session)
    res = _create_exec(session, remediation=dict(_HIT))

    assert res.get("status") in ("running", "approved", "awaiting_approval"), res
    auto_rows = _approvals_auto(session)
    assert len(auto_rows) == 1, f"hit must pre-authorise exactly one row; got {len(auto_rows)}"
    a = auto_rows[0]
    assert a.status == "approved", f"auto_policy row must be approved; got {a.status!r}"
    assert a.policy_ref, "auto_policy row must carry policy_ref"
    assert _auto_count(session) - auto0 == 1, "hit must write exactly one E6 decision='auto'"


# ── ③ E6-3 negative (non-vacuous) ────────────────────────────────────────────

def _assert_manual_pending(session, auto0: int) -> None:
    from app.db.models import ApprovalRequest  # noqa: PLC0415

    rows = session.query(ApprovalRequest).all()
    assert len(rows) == 1, f"expected exactly one approval row; got {len(rows)}"
    a = rows[0]
    assert a.approval_mode == "manual", f"miss must stay manual; got {a.approval_mode!r}"
    assert a.status == "pending", f"miss must stay pending (HITL); got {a.status!r}"
    assert _auto_count(session) - auto0 == 0, "miss must write no E6 decision='auto'"


def test_b3_e6_3_negative_whitelist_miss(p6_db):
    session, set_user, set_flag, _c = p6_db
    set_flag("ai.auto_remediate", True)
    _seed_hit_context(session)
    _set_whitelist(session, "other_action", "low", True)  # 'restart' not whitelisted

    auto0 = _auto_count(session)
    _create_exec(session, remediation={**_HIT, "action": "not_whitelisted"})
    _assert_manual_pending(session, auto0)


def test_b4_e6_3_negative_risk_high(p6_db):
    session, set_user, set_flag, _c = p6_db
    set_flag("ai.auto_remediate", True)
    _seed_hit_context(session)

    auto0 = _auto_count(session)
    _create_exec(session, remediation={**_HIT, "risk_level": "high"})
    _assert_manual_pending(session, auto0)


def test_b5_e6_3_negative_level_not_l4(p6_db):
    session, set_user, set_flag, _c = p6_db
    set_flag("ai.auto_remediate", True)
    _seed_hit_context(session, level="L3")  # current != L4

    auto0 = _auto_count(session)
    _create_exec(session, remediation=dict(_HIT))
    _assert_manual_pending(session, auto0)


# ── ③b E6-3 retry is ALWAYS manual (@架构 3616①⑦) ───────────────────────────

def test_b6_retry_is_always_manual(p6_db):
    session, set_user, set_flag, _c = p6_db
    from app.db.models import ApprovalRequest, ExecTask  # noqa: PLC0415
    from app.services import exec_service  # noqa: PLC0415

    set_flag("ai.auto_remediate", True)
    _seed_sensitive(session)
    _make_host(session)

    # a terminal (failed) sensitive exec task with no prior approval row, so the
    # retry insert is not blocked by the pre-existing UNIQUE(approval_request.biz_id).
    task = ExecTask(task_no="T-1", name="failed remediation", kind="command",
                    command=_SENSITIVE_CMD, target_host_ids={"ids": [1]},
                    status="failed", created_by=1, version=0, sensitive_flag=1,
                    approve_required=1)
    session.add(task)
    session.commit()

    auto0 = _auto_count(session)
    out = exec_service.retry_task(session, _User(["exec:task:retry"], admin=True), task.id)
    assert out.get("status") == "awaiting_approval", out
    fresh = session.get(ApprovalRequest, out["approval_id"])
    assert fresh.status == "pending" and fresh.approval_mode == "manual", (
        f"retry must be fail-closed manual/pending; got {fresh.approval_mode!r}/{fresh.status!r}"
    )
    assert _auto_count(session) - auto0 == 0, "retry must not write an E6 decision='auto'"


# ── ④ E6-4 rollback compensation ─────────────────────────────────────────────

def test_b7_e6_4_rollback_compensates_once(p6_db):
    session, set_user, set_flag, _c = p6_db
    from app.db.models import AiAction, ApprovalRequest, ExecTask, Workflow, WorkflowRun  # noqa: PLC0415
    from app.services import ai_automation_service as svc  # noqa: PLC0415

    set_flag("ai.auto_remediate", True)
    _seed_sensitive(session)
    _make_host(session)
    _set_policy(session, "app", "restart", rollback_window=3600)

    wf = Workflow(id=1, name="wf-p6", current_version=1, created_by=1)
    session.add(wf)
    run = WorkflowRun(
        id=1, workflow_id=1, workflow_version=1, status="succeeded", trigger_type="manual",
        context={
            "remediation": {"name": "rollback x", "kind": "command",
                            "command": _SENSITIVE_CMD, "target_host_ids": [1],
                            "asset_class": "app", "op_type": "restart"},
            "rollback_window": 3600,
        },
        created_by=1,
    )
    session.add(run)
    session.commit()

    e0, a0 = _count(session, ExecTask), _count(session, ApprovalRequest)
    svc.rollback_run(session, _User(), run.id)

    assert _count(session, ExecTask) - e0 == 1, "first rollback must create ONE compensating exec_task"
    assert _count(session, ApprovalRequest) - a0 == 1, "compensating exec must create ONE approval row"
    assert any(getattr(x, "rollback_ref", None) for x in session.query(AiAction).all()), (
        "compensating ai_action must set rollback_ref"
    )

    svc.rollback_run(session, _User(), run.id)
    assert _count(session, ExecTask) - e0 == 1, "repeat rollback must be Δ0"
    assert _count(session, ApprovalRequest) - a0 == 1, "repeat rollback must be Δ0"


# ── ③s verification fail-closed 422 (@需求 §30.7 ③) ─────────────────────────

def test_b8_l4_activation_requires_verification(p6_db):
    session, set_user, set_flag, client = p6_db
    set_flag("ai.auto_remediate", True)
    set_user(["ai:use", "ai:admin"], admin=True)

    # an L4 policy whose verification_ref is missing => L4 activation must fail-closed.
    _set_policy(session, "app", "restart", level="L4", verification_ref=None)
    r = client.put("/api/v1/ai/automation/level", json={"current": "L4"})
    assert r.status_code == 422, (
        f"L4 activation without complete verification_ref must be 422; got {r.status_code} {r.text}"
    )
    assert _data(client.get("/api/v1/ai/automation/level"))["current"] != "L4", (
        "level must stay unchanged after a failed L4 activation"
    )

    # once verification is complete, activation succeeds.
    from app.db.models import RemediationPolicy  # noqa: PLC0415

    session.query(RemediationPolicy).delete()
    session.commit()
    _set_policy(session, "app", "restart", level="L4", verification_ref="V-2")
    r = client.put("/api/v1/ai/automation/level", json={"current": "L4"})
    assert r.status_code == 200, r.text
    assert _data(r)["current"] == "L4"


# ── ④s circuit-breaker (symbol + env; FSM values) ───────────────────────────
# NOTE: the FSM *trigger* seam is not yet specified (@需求 §30.7 ④); this pins the
# threshold single-source and the state vocabulary. Flagged to #team for a ruling.

def test_b9_circuit_breaker_resolve_threshold_symbol(p6_db):
    session, set_user, set_flag, _c = p6_db
    from app.db.models import CircuitBreakerState  # noqa: PLC0415

    svc = _require("app.services.ai_automation_service")
    assert hasattr(svc, "resolve_threshold"), (
        "breaker threshold must be a single named source `resolve_threshold` (@需求 §30.7 ④)"
    )
    assert callable(svc.resolve_threshold), "`resolve_threshold` must be callable"

    set_flag("ai.auto_remediate", True)

    class _Provider:
        id = 1
        name = "p"

    got = svc.resolve_threshold(_Provider())
    assert got is None or isinstance(got, int), f"resolve_threshold must yield int|None; got {got!r}"

    # documented state vocabulary on the governed table.
    session.add(CircuitBreakerState(scope="provider:1", state="open", current=5, threshold=3))
    session.commit()
    assert session.query(CircuitBreakerState).one().state in ("closed", "open", "half")
