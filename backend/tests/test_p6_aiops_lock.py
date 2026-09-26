r"""P6 (AIOps E6 受控自动处置·L4 + E7/E8 weighted) contract locks — @单元 lock-first, add-only.

Frozen contract: @架构 **P6 tuple r1** (seq3560) + @需求 **§30** (`p6-requirements-product-design-v0.1.md`,
att `att_xu8e5uz7faa3xa`). Base = release **M11 `6740d22a3854798ab2a49725b8d397d37238aa15`** (master).

Pinned surface (r1 A–F):
  A perms        : shared `ai:use`/`ai:admin` (unchanged) => 16 endpoint codes; per-route:
                   level GET ai:use / PUT ai:admin ; whitelist GET|POST ai:admin ;
                   whitelist/{item_id} PUT|DELETE ai:admin ; dry-run POST ai:use ;
                   runs/{run_id}/rollback POST ai:admin ; circuit-breaker GET ai:use
  B flag gate    : routes ALWAYS registered ((A)) => committed/served `paths` == 173;
                   gate order auth(401) -> flag(400|403) -> not-404; flag off != 404
  C① enums/tables: `RISK_LEVELS=("low","medium","high")` in `app/db/models/ai.py`
                   (re-exported via `__init__`); `APPROVAL_MODES=("auto_policy","manual")`
                   and `L4_AUTO_RISK_LEVELS=("low",)` net-new in the leaf module
                   `app/services/ai_automation_constants.py`; `AI_ACTION_DECISIONS`
                   add-only += "dry_run"; L4 gate: `risk_level in L4_AUTO_RISK_LEVELS`
                   => auto_policy (inline `"low"` forbidden)
     migration   : `revision="P6_REV"`, `down_revision="f5a6b7c8d9e0"` (single head, C set,
                   add-only); 4 NEW tables `remediation_policy`/`automation_whitelist`/
                   `automation_level`/`circuit_breaker_state`; NO `remediation_run`
                   (reuse `workflow_run`); `ai_action` add-only cols
                   `approval_mode`/`policy_ref`/`verification_ref`/`rollback_ref`
  C② approval    : REUSE `ApprovalRequest` (add cols `approval_mode` default 'manual' /
                   `policy_ref`; auto_policy => `status=approved`); E6 adds ZERO
                   `ApprovalRequest(` construction sites — authoritative 6 sites only;
                   exec gate `orchestrator.py::_approval_gate`; dispatch `approval_service.py`
                   `_approve_exec` / `_approve_linkages`
  C④ flag        : single `ai.auto_remediate` (default False); shadow = governed
                   `mode: shadow|live`, NO sub-flag
  D served tier  : leaf module `app/services/ai_automation_constants.py` with
                   `P6_REV` + `APPROVAL_MODES` (symbols; probe = isolated subprocess)

EXPECTED: clean **RED** until the P6 backend lands (add-only). Import-guarded so a run
reports assertion failures, not collection errors. Offline only (no live PG/Redis; no
migrations applied; no network).

Run (backend checkout, backend venv):
    python -m pytest tests/test_p6_aiops_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import pkgutil
import re

import pytest

from tests.openapi_baseline import M6_P3_4_KEYS


# ── helpers ──────────────────────────────────────────────────────────────────

def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


def _require(mod: str):
    obj = _try(mod)
    if isinstance(obj, Exception):
        pytest.fail(f"P6 lock: `{mod}` unavailable: {obj!r}")
    return obj


_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_VERSIONS_DIR = _BACKEND / "alembic" / "versions"

# release anchor this lock is written against
_M11 = "6740d22a3854798ab2a49725b8d397d37238aa15"
# P5/P5.1 single head; P6 descends directly from it
_P6_PARENT = "f5a6b7c8d9e0"
# served tier symbol value (r1 D: `P6_REV = "P6_REV"`)
_P6_REV_VALUE = "P6_REV"
_P6_FLAG = "ai.auto_remediate"
_P6_PERMS = {"ai:use", "ai:admin"}
_LEAF_MODULE = "app.services.ai_automation_constants"

# 14 (P3-6 op-level) + 2 shared ai (P4) => 16 named endpoint codes (r1 A/⑥; unchanged in P6)
_P36_OP_CODES = {
    "cicd:provider:list", "cicd:provider:add", "cicd:provider:edit",
    "cicd:provider:del", "cicd:provider:test",
    "release:list", "release:add", "release:view", "release:canary",
    "release:promote", "release:rollback", "release:cancel",
    "release:deploy", "release:fail",
}

# frozen vocabularies (r1 C①)
RISK_LEVELS = ("low", "medium", "high")
APPROVAL_MODES = ("auto_policy", "manual")
L4_AUTO_RISK_LEVELS = ("low",)
AI_ACTION_DECISIONS = ("adopted", "rejected", "auto", "dry_run")

# r1 C①: exactly 4 NEW tables; `remediation_run` is explicitly NOT created.
P6_TABLES = ("remediation_policy", "automation_whitelist", "automation_level", "circuit_breaker_state")
P6_FORBIDDEN_TABLES = ("remediation_run",)
AI_ACTION_NEW_COLS = {"approval_mode", "policy_ref", "verification_ref", "rollback_ref"}
APPROVAL_NEW_COLS = {"approval_mode", "policy_ref"}
WHITELIST_COLS = {"action", "risk_level", "enabled"}

# r1 C②: authoritative ApprovalRequest construction sites (E6 must add none)
APPROVAL_REQUEST_SITES = {
    "services/exec_service.py": 2,
    "services/schedule_service.py": 2,
    "services/terminal_service.py": 1,
    "services/workflow_engine.py": 1,
}

# r1 A/B/C③: exactly 6 new URL keys (path templates) => paths 167 -> 173
P6_PATHS = {
    r"/api/v1/ai/automation/level": {"get", "put"},
    r"/api/v1/ai/automation/whitelist": {"get", "post"},
    r"/api/v1/ai/automation/whitelist/\{[^}]+\}": {"put", "delete"},
    r"/api/v1/ai/automation/dry-run": {"post"},
    r"/api/v1/ai/automation/runs/\{[^}]+\}/rollback": {"post"},
    r"/api/v1/ai/automation/circuit-breaker": {"get"},
}
_METHODS = {"get", "post", "put", "delete", "patch"}

# frozen OpenAPI URL-key baseline at M11 (167 keys) — `removed==[]` guard for r1 C③.
M11_KEYS = (
    '/api/v1/ai/actions',
    '/api/v1/ai/feedback',
    '/api/v1/approvals',
    '/api/v1/approvals/rules',
    '/api/v1/approvals/rules/{rule_id}',
    '/api/v1/approvals/{approval_id}',
    '/api/v1/approvals/{approval_id}/approve',
    '/api/v1/approvals/{approval_id}/cancel',
    '/api/v1/approvals/{approval_id}/reject',
    '/api/v1/assets/cmdb/impact',
    '/api/v1/assets/cmdb/topology',
    '/api/v1/assets/credentials',
    '/api/v1/assets/credentials/{cred_id}',
    '/api/v1/assets/groups',
    '/api/v1/assets/groups/tree',
    '/api/v1/assets/groups/{group_id}',
    '/api/v1/assets/hosts',
    '/api/v1/assets/hosts/export',
    '/api/v1/assets/hosts/import',
    '/api/v1/assets/hosts/stats',
    '/api/v1/assets/hosts/{host_id}',
    '/api/v1/assets/hosts/{host_id}/conn',
    '/api/v1/assets/hosts/{host_id}/connector',
    '/api/v1/assets/hosts/{host_id}/executors',
    '/api/v1/assets/options',
    '/api/v1/assets/relations',
    '/api/v1/assets/relations/{relation_id}',
    '/api/v1/auth/ldap/login',
    '/api/v1/auth/login',
    '/api/v1/auth/logout',
    '/api/v1/auth/me',
    '/api/v1/auth/oauth/{provider}/callback',
    '/api/v1/auth/oauth/{provider}/login',
    '/api/v1/auth/password',
    '/api/v1/auth/providers',
    '/api/v1/auth/providers/{provider_id}',
    '/api/v1/auth/providers/{provider_id}/status',
    '/api/v1/auth/providers/{provider_id}/test',
    '/api/v1/auth/refresh',
    '/api/v1/cicd/providers',
    '/api/v1/cicd/providers/{provider_id}',
    '/api/v1/cicd/providers/{provider_id}/test',
    '/api/v1/cicd/webhooks/{provider}',
    '/api/v1/dashboard/recent-approvals',
    '/api/v1/dashboard/recent-tasks',
    '/api/v1/dashboard/stats',
    '/api/v1/dashboard/task-trend',
    '/api/v1/events',
    '/api/v1/events/{event_id}',
    '/api/v1/exec/tasks',
    '/api/v1/exec/tasks/{task_id}',
    '/api/v1/exec/tasks/{task_id}/hosts/{task_host_id}/logs',
    '/api/v1/exec/tasks/{task_id}/hosts/{task_host_id}/ws-token',
    '/api/v1/exec/tasks/{task_id}/retry',
    '/api/v1/exec/tasks/{task_id}/stats',
    '/api/v1/exec/tasks/{task_id}/stop',
    '/api/v1/kb/ai/answer',
    '/api/v1/kb/articles',
    '/api/v1/kb/articles/{article_id}',
    '/api/v1/kb/articles/{article_id}/rollback',
    '/api/v1/kb/articles/{article_id}/versions',
    '/api/v1/kb/articles/{article_id}/versions/{version}',
    '/api/v1/kb/categories',
    '/api/v1/kb/categories/{category_id}',
    '/api/v1/kb/search',
    '/api/v1/kb/search/semantic',
    '/api/v1/monitor/adapters',
    '/api/v1/monitor/adapters/{adapter_id}',
    '/api/v1/monitor/adapters/{adapter_id}/status',
    '/api/v1/monitor/adapters/{adapter_id}/test',
    '/api/v1/monitor/alerts',
    '/api/v1/monitor/alerts/aggregate',
    '/api/v1/monitor/alerts/{alert_id}',
    '/api/v1/monitor/alerts/{alert_id}/acknowledge',
    '/api/v1/monitor/alerts/{alert_id}/ai/rca',
    '/api/v1/monitor/alerts/{alert_id}/events',
    '/api/v1/monitor/alerts/{alert_id}/resolve',
    '/api/v1/monitor/events',
    '/api/v1/monitor/events/{event_id}',
    '/api/v1/monitor/ingest/{adapter_id}',
    '/api/v1/monitor/metrics',
    '/api/v1/monitor/metrics/current',
    '/api/v1/monitor/rules',
    '/api/v1/monitor/rules/{rule_id}',
    '/api/v1/monitor/rules/{rule_id}/status',
    '/api/v1/monitor/rules/{rule_id}/test',
    '/api/v1/monitor/ws-token',
    '/api/v1/notify/channels',
    '/api/v1/notify/channels/{channel_id}',
    '/api/v1/notify/channels/{channel_id}/status',
    '/api/v1/notify/channels/{channel_id}/test',
    '/api/v1/notify/records',
    '/api/v1/notify/records/{record_id}/resend',
    '/api/v1/releases',
    '/api/v1/releases/{release_id}',
    '/api/v1/releases/{release_id}/canary',
    '/api/v1/releases/{release_id}/cancel',
    '/api/v1/releases/{release_id}/deploy',
    '/api/v1/releases/{release_id}/fail',
    '/api/v1/releases/{release_id}/promote',
    '/api/v1/releases/{release_id}/rollback',
    '/api/v1/schedules',
    '/api/v1/schedules/{schedule_id}',
    '/api/v1/schedules/{schedule_id}/run-now',
    '/api/v1/schedules/{schedule_id}/runs',
    '/api/v1/schedules/{schedule_id}/runs/{run_id}/retry',
    '/api/v1/schedules/{schedule_id}/status',
    '/api/v1/scripts',
    '/api/v1/scripts/{script_id}',
    '/api/v1/scripts/{script_id}/rollback',
    '/api/v1/scripts/{script_id}/test',
    '/api/v1/scripts/{script_id}/versions',
    '/api/v1/scripts/{script_id}/versions/{version}',
    '/api/v1/system/audit-logs',
    '/api/v1/system/audit-logs/export',
    '/api/v1/system/audit-logs/{log_id}',
    '/api/v1/system/permissions',
    '/api/v1/system/roles',
    '/api/v1/system/roles/{role_id}',
    '/api/v1/system/roles/{role_id}/groups',
    '/api/v1/system/roles/{role_id}/permissions',
    '/api/v1/system/users',
    '/api/v1/system/users/{user_id}',
    '/api/v1/system/users/{user_id}/password',
    '/api/v1/system/users/{user_id}/roles',
    '/api/v1/system/users/{user_id}/status',
    '/api/v1/terminals',
    '/api/v1/terminals/{session_id}',
    '/api/v1/terminals/{session_id}/close',
    '/api/v1/terminals/{session_id}/recording',
    '/api/v1/terminals/{session_id}/token',
    '/api/v1/tickets',
    '/api/v1/tickets/{ticket_id}',
    '/api/v1/tickets/{ticket_id}/accept',
    '/api/v1/tickets/{ticket_id}/ai/similar',
    '/api/v1/tickets/{ticket_id}/ai/suggest',
    '/api/v1/tickets/{ticket_id}/assign',
    '/api/v1/tickets/{ticket_id}/attachments',
    '/api/v1/tickets/{ticket_id}/cancel',
    '/api/v1/tickets/{ticket_id}/close',
    '/api/v1/tickets/{ticket_id}/comments',
    '/api/v1/tickets/{ticket_id}/done',
    '/api/v1/tickets/{ticket_id}/process',
    '/api/v1/tickets/{ticket_id}/refs',
    '/api/v1/tickets/{ticket_id}/reopen',
    '/api/v1/transfer/packages',
    '/api/v1/transfer/packages/{package_id}',
    '/api/v1/transfer/tasks',
    '/api/v1/transfer/tasks/mine',
    '/api/v1/transfer/tasks/{task_id}',
    '/api/v1/transfer/tasks/{task_id}/hosts/{transfer_host_id}/logs',
    '/api/v1/transfer/tasks/{task_id}/hosts/{transfer_host_id}/retry',
    '/api/v1/transfer/tasks/{task_id}/hosts/{transfer_host_id}/ws-token',
    '/api/v1/transfer/tasks/{task_id}/stats',
    '/api/v1/transfer/tasks/{task_id}/stop',
    '/api/v1/workflow-runs',
    '/api/v1/workflow-runs/{run_id}',
    '/api/v1/workflow-runs/{run_id}/callback/{node_key}',
    '/api/v1/workflow-runs/{run_id}/cancel',
    '/api/v1/workflow-runs/{run_id}/retry',
    '/api/v1/workflow-runs/{run_id}/ws-token',
    '/api/v1/workflows',
    '/api/v1/workflows/ai/suggest',
    '/api/v1/workflows/{workflow_id}',
    '/api/v1/workflows/{workflow_id}/rollback',
    '/api/v1/workflows/{workflow_id}/run',
    '/api/v1/workflows/{workflow_id}/versions',
)

if len(M11_KEYS) != 167:  # pragma: no cover — freeze guard for the M11 baseline
    raise RuntimeError(f"M11 openapi baseline must have exactly 167 keys; got {len(M11_KEYS)}")


# ── P: permission codes + seed tree counts (r1 A/⑥) ──────────────────────────

def _seed():
    seed = _try("app.db.seed")
    if isinstance(seed, Exception):
        pytest.fail(f"P6 lock: app.db.seed unavailable: {seed}")
    return seed


def _perm_codes() -> set[str]:
    seed = _seed()
    acc: set[str] = set()

    def walk(nodes):
        for node in nodes or []:
            acc.add(node[0])
            walk(node[5] if len(node) > 5 else [])

    walk(getattr(seed, "PERMISSION_TREE", []))
    return acc


def test_p1_ai_permission_codes_registered():
    codes = _perm_codes()
    missing = _P6_PERMS - codes
    assert not missing, f"P6 reuses ai perms; missing from PERMISSION_TREE: {sorted(missing)}"


def test_p2_permission_total_still_16():
    """r1 A/⑥: API perms unchanged == 16 (14 P3-6 op codes + ai:use/ai:admin)."""
    assert len(_P36_OP_CODES | _P6_PERMS) == 16, "14 (P3-6) + 2 (ai:use/ai:admin) == 16"
    codes = _perm_codes()
    assert _P6_PERMS <= codes, f"ai perms not seeded: {sorted(_P6_PERMS - codes)}"
    seeded = (_P36_OP_CODES | _P6_PERMS) & codes
    assert len(seeded) == 16, (
        f"seeded endpoint-code set must be exactly 16 (P6 does not add perms); got {len(seeded)}: "
        f"{sorted(seeded)}"
    )


def test_p3_seed_menu_button_counts_unchanged():
    """r1 ⑥ / @前端 3532: FE reuses ai:admin; no new seed menu/button => 27/112 unchanged."""
    tree = getattr(_seed(), "PERMISSION_TREE", [])
    menus = [node[0] for node in tree]
    buttons = [child[0] for node in tree for child in node[5]]
    assert len(menus) == 27, f"menus must stay 27; got {len(menus)}"
    assert len(buttons) == 112, f"buttons must stay 112; got {len(buttons)}"


# ── F: single flag, default False, no shadow sub-flag (r1 C④) ────────────────

def test_f1_p6_flag_default_false():
    rules = getattr(_seed(), "DEFAULT_CONFIG_RULES", {})
    entry = rules.get(_P6_FLAG)
    assert entry is not None, f"`{_P6_FLAG}` must be seeded (add-only)"
    assert entry.get("value") is False, (
        f"`{_P6_FLAG}` default must be False; got {entry.get('value')!r}"
    )


def test_f2_no_shadow_subflag():
    """r1 C④: shadow == governed `mode: shadow|live`, NOT a sub-flag."""
    rules = getattr(_seed(), "DEFAULT_CONFIG_RULES", {})
    offenders = [
        k for k in rules
        if k.startswith(_P6_FLAG + ".") or "shadow" in k.lower()
    ]
    assert not offenders, (
        f"shadow must be a governed `mode` value, not a flag; unexpected config key(s): {offenders}"
    )


def test_f3_prior_ai_flags_still_false():
    rules = getattr(_seed(), "DEFAULT_CONFIG_RULES", {})
    for flag in ("ai.enabled", "ai.rca", "ai.playbook"):
        assert rules.get(flag, {}).get("value") is False, f"{flag} must remain default False"


def test_f4_p6_flag_registered_in_ai_gate():
    """r1 C④ / @后端 3563: the single flag must join `ai_gate.AI_FLAGS` (feature-first gate
    vocabulary) and NOT be a shadow sub-flag."""
    mod = _require("app.services.ai_gate")
    flags = tuple(getattr(mod, "AI_FLAGS", ()) or ())
    assert _P6_FLAG in flags, (
        f"`{_P6_FLAG}` must be registered in `ai_gate.AI_FLAGS` (feature-first gate); "
        f"got {flags!r}"
    )
    offenders = [f for f in flags if "shadow" in f.lower() or f.startswith(_P6_FLAG + ".")]
    assert not offenders, f"no shadow sub-flag allowed (r1 C④); got {offenders}"


# ── E: frozen vocabularies (r1 C①) ───────────────────────────────────────────

def _ai_models():
    return _require("app.db.models.ai")


def test_e1_risk_levels_single_source():
    mod = _ai_models()
    got = getattr(mod, "RISK_LEVELS", None)
    assert got == RISK_LEVELS, (
        f"`app.db.models.ai.RISK_LEVELS` must be {RISK_LEVELS} (lowercase, frozen, inlining "
        f"forbidden); got {got!r}"
    )


def test_e1b_risk_levels_reexported():
    models = _require("app.db.models")
    got = getattr(models, "RISK_LEVELS", None)
    assert got == RISK_LEVELS, (
        f"`app.db.models.RISK_LEVELS` must be re-exported == {RISK_LEVELS}; got {got!r}"
    )


def test_e2_ai_action_decisions_add_only_dry_run():
    """r1 C①: `AI_ACTION_DECISIONS` add-only += "dry_run" (existing 3 preserved)."""
    mod = _ai_models()
    got = tuple(getattr(mod, "AI_ACTION_DECISIONS", ()) or ())
    assert set(got) == set(AI_ACTION_DECISIONS), (
        f"AI_ACTION_DECISIONS must be exactly {AI_ACTION_DECISIONS}; got {got!r}"
    )
    assert set(("adopted", "rejected", "auto")) <= set(got), "existing decisions must be preserved"


def test_e3_leaf_module_approval_modes():
    mod = _require(_LEAF_MODULE)
    got = getattr(mod, "APPROVAL_MODES", None)
    assert tuple(got or ()) == APPROVAL_MODES, (
        f"`{_LEAF_MODULE}.APPROVAL_MODES` must be {APPROVAL_MODES}; got {got!r}"
    )


def test_e4_l4_auto_risk_levels_pinned_in_leaf():
    """r1.6 (@架构 664b07bc): the L4 auto set is a NET-NEW named constant
    `L4_AUTO_RISK_LEVELS = ("low",)` in the leaf module (same module as APPROVAL_MODES) —
    only `low` maps to auto_policy; inline `"low"` literals are forbidden (so the lock must
    pin the symbol, NOT degrade to `RISK_LEVELS`)."""
    leaf = _require(_LEAF_MODULE)
    got = getattr(leaf, "L4_AUTO_RISK_LEVELS", None)
    assert tuple(got or ()) == L4_AUTO_RISK_LEVELS, (
        f"`{_LEAF_MODULE}.L4_AUTO_RISK_LEVELS` must be {L4_AUTO_RISK_LEVELS} (r1.6, single "
        f"source = leaf module); got {got!r}"
    )


# ── M: tables / columns (r1 C①/C②) ──────────────────────────────────────────

def _tables():
    try:
        import app.db.models  # noqa: F401,PLC0415
        from app.db.base import Base  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P6 lock: app.db.base/models unavailable: {exc}")
    return Base.metadata.tables


def test_m1_p6_tables_registered():
    tables = _tables()
    missing = [t for t in P6_TABLES if t not in tables]
    assert not missing, f"P6 must define {list(P6_TABLES)}; missing {missing}"


def test_m1b_no_remediation_run_table():
    """r1 C①: no `remediation_run` — reuse existing `workflow_run`."""
    tables = _tables()
    offenders = [t for t in P6_FORBIDDEN_TABLES if t in tables]
    assert not offenders, f"r1 forbids {offenders}; reuse `workflow_run` instead"


def test_m2_ai_action_new_columns():
    t = _tables().get("ai_action")
    if t is None:
        pytest.fail("P6 lock: table `ai_action` missing")
    miss = AI_ACTION_NEW_COLS - set(t.columns.keys())
    assert not miss, f"ai_action must add {sorted(AI_ACTION_NEW_COLS)}; missing {sorted(miss)}"


def test_m3_approval_request_new_columns():
    t = _tables().get("approval_request")
    if t is None:
        pytest.fail("P6 lock: table `approval_request` missing")
    miss = APPROVAL_NEW_COLS - set(t.columns.keys())
    assert not miss, f"approval_request must add {sorted(APPROVAL_NEW_COLS)}; missing {sorted(miss)}"
    col = t.columns.get("approval_mode")
    if col is not None and col.default is not None:
        assert getattr(col.default, "arg", None) == "manual", (
            "approval_request.approval_mode default must be 'manual' (r1 C②); got "
            f"{getattr(col.default, 'arg', None)!r}"
        )


def test_m4_whitelist_columns():
    t = _tables().get("automation_whitelist")
    if t is None:
        pytest.fail("P6 lock: table `automation_whitelist` missing")
    miss = WHITELIST_COLS - set(t.columns.keys())
    assert not miss, (
        f"automation_whitelist must carry {sorted(WHITELIST_COLS)}; missing {sorted(miss)}"
    )


def test_m5_new_approval_columns_plain_string_no_reverse_dep():
    """r1.2 / @reviewer 3570: `approval_mode`/`policy_ref` (and ai_action's) are plain
    String columns (comment-enum), NOT CheckConstraint/Enum referencing the services-layer
    `APPROVAL_MODES` (avoids a models->services reverse dependency; same shape as
    `AiAction.decision`)."""
    from sqlalchemy import CheckConstraint, String  # noqa: PLC0415

    tables = _tables()
    targets = (
        ("approval_request", APPROVAL_NEW_COLS),
        ("ai_action", {"approval_mode", "policy_ref"}),
    )
    problems = []
    for tname, cols in targets:
        t = tables.get(tname)
        if t is None:
            problems.append(f"{tname}: table missing")
            continue
        for c in cols:
            col = t.columns.get(c)
            if col is None:
                problems.append(f"{tname}.{c}: missing")
                continue
            if not isinstance(col.type, String):
                problems.append(
                    f"{tname}.{c}: must be plain String (comment-enum), got {col.type!r}"
                )
        for cons in t.constraints:
            if isinstance(cons, CheckConstraint) and "APPROVAL_MODES" in str(cons.sqltext):
                problems.append(
                    f"{tname}: CheckConstraint references APPROVAL_MODES (models->services dep)"
                )
    assert not problems, "reverse-dep guard: " + "; ".join(problems)


def _grep_files(root: pathlib.Path, needle: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    for py in root.rglob("*.py"):
        try:
            n = py.read_text(encoding="utf-8").count(needle)
        except Exception:  # noqa: BLE001
            continue
        if n:
            try:
                rel = py.relative_to(root).as_posix()
            except ValueError:  # pragma: no cover
                rel = py.as_posix()
            hits[rel] = n
    return hits


def test_m6_check_constraint_baseline_unchanged():
    """r1.4 (a) (@架构 3572 / @reviewer 3573): in `app/db`, `CheckConstraint` occurs ONLY in
    `models/cmdb.py` (import + usage) — E6 adds none (new cols are plain String). File-set
    form (not `== {cmdb.py:34}`) so the import line cannot false-red."""
    root = pathlib.Path(_require("app").__file__).resolve().parent / "db"
    hits = _grep_files(root, "CheckConstraint")
    assert set(hits) == {"models/cmdb.py"}, (
        "`CheckConstraint` in app/db must remain solely in models/cmdb.py (import + usage); "
        f"E6 must add none; got {hits}"
    )


def test_m7_models_layer_no_services_reverse_dependency():
    """r1.4 (b) (@架构 3572 / @reviewer 3573): the models layer must not reference
    `app.services` (substring form covers from/import/attribute) — `APPROVAL_MODES` stays a
    leaf in services, not pulled into models."""
    root = pathlib.Path(_require("app").__file__).resolve().parent / "db" / "models"
    hits = _grep_files(root, "app.services")
    assert not hits, f"models layer must not depend on services (reverse dep); hits: {hits}"


# ── A: openapi surface (r1 A/B/C③) ───────────────────────────────────────────

def _openapi_paths() -> dict:
    try:
        from app.main import app  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P6 lock: app.main unavailable: {exc}")
    return app.openapi().get("paths", {})


def test_a1_p6_paths_present_with_methods():
    paths = _openapi_paths()
    problems = []
    for pat, want in P6_PATHS.items():
        rx = re.compile(rf"^{pat}$")
        hits = [k for k in paths if rx.match(k)]
        if not hits:
            problems.append(f"missing {pat}")
            continue
        have = {m for k in hits for m in paths[k] if m in _METHODS}
        miss = want - have
        if miss:
            problems.append(f"{pat} missing methods {sorted(miss)} (have {sorted(have)})")
    assert not problems, "P6 openapi surface incomplete: " + "; ".join(problems)


def test_a2_paths_count_173_and_no_removed():
    """r1 C③: N=6 => paths 167 -> 173, EXACT; no M11 key removed ((A): routes always
    registered => committed/served paths is 173 regardless of the flag)."""
    paths = _openapi_paths()
    assert len(paths) == 173, (
        f"P6 paths must be exactly 173 (167 + 6 automation URL keys); got {len(paths)}"
    )
    removed = set(M11_KEYS) - set(paths)
    assert not removed, f"r1 C③ removed==[] violated; removed={sorted(removed)}"
    m6_removed = set(M6_P3_4_KEYS) - set(paths)
    assert not m6_removed, f"openapi must not shrink below M6 baseline; removed={sorted(m6_removed)}"


def test_a3_rollback_key_is_run_id():
    """r1 C③: rollback path key uses `{run_id}` (the `{id}` spelling is void)."""
    paths = _openapi_paths()
    assert "/api/v1/ai/automation/runs/{run_id}/rollback" in paths, (
        "rollback path key must be `/api/v1/ai/automation/runs/{run_id}/rollback`"
    )
    assert "/api/v1/ai/automation/runs/{id}/rollback" not in paths, (
        "`{id}` spelling must not exist (r1 C③ unified on `{run_id}`)"
    )


# ── G: migration graph + env allow-list homes (r1 C①) ────────────────────────

def _revision_graph() -> dict[str, str | None]:
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(None|["\']([^"\']*)["\'])', txt, re.M)
        if not m:
            continue
        parent = None
        if d:
            parent = None if d.group(1) == "None" else d.group(2)
        revs[m.group(1)] = parent
    return revs


def test_g1_p6_migration_single_head_from_p5():
    revs = _revision_graph()
    assert revs, "alembic revisions not found"
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert len(heads) == 1, f"migration must keep a single head; got {heads}"
    head = heads[0]
    assert revs.get(head) == _P6_PARENT, (
        f"new head {head!r} must descend directly from P5 head {_P6_PARENT}; "
        f"got parent {revs.get(head)!r}"
    )
    # the new head's rev value must equal the served-tier symbol (single source of truth)
    leaf = _require(_LEAF_MODULE)
    assert head == getattr(leaf, "P6_REV", None), (
        f"migration head {head!r} must equal leaf `P6_REV` "
        f"({getattr(leaf, 'P6_REV', None)!r}) — single source of truth"
    )


def test_g2_env_contract_lock_pins_p6_rev_symbol():
    p = pathlib.Path(__file__).resolve().parent / "test_live_env_contract_lock.py"
    spec = importlib.util.spec_from_file_location("_p6_live_contract_lock", p)
    if spec is None or spec.loader is None:
        pytest.fail("P6 lock: cannot load test_live_env_contract_lock.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sym = getattr(mod, "P6_REV", None)
    assert sym is not None, (
        "test_live_env_contract_lock.py must expose a named `P6_REV` symbol (r1 C① 4 homes)"
    )
    assert sym in mod.MIGRATION_LIVE_FORBIDDEN, f"{sym!r} must be a member of C (forbidden)"
    assert mod.MIGRATION_LIVE_APPLICABLE & mod.MIGRATION_LIVE_FORBIDDEN == set(), (
        "B ∩ C must stay empty"
    )


def test_g3_smoke_pins_p6_rev_symbol():
    """r1 C① «4 homes sync»: the runtime gate `live_readiness_smoke.py` must also carry the
    P6 rev as a named symbol in its C set (single-source cross-home; docs covered by the
    existing `test_live_env_allowlist_single_source_lock`)."""
    smoke_path = _BACKEND / "tools" / "live_readiness_smoke.py"
    if not smoke_path.is_file():
        pytest.fail(f"P6 lock: {smoke_path} not found")
    spec = importlib.util.spec_from_file_location("_p6_live_smoke", smoke_path)
    if spec is None or spec.loader is None:
        pytest.fail("P6 lock: cannot load tools/live_readiness_smoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sym = getattr(mod, "P6_REV", None)
    assert sym is not None, "live_readiness_smoke.py must expose a named `P6_REV` symbol"
    assert sym in mod.MIGRATION_LIVE_FORBIDDEN, f"{sym!r} must be a member of the smoke C set"


# ── S: served-tier leaf symbol (r1 D) ────────────────────────────────────────

def test_s1_leaf_module_is_pure_and_pins_symbols():
    mod = _require(_LEAF_MODULE)
    assert getattr(mod, "P6_REV", None) == _P6_REV_VALUE, (
        f"`{_LEAF_MODULE}.P6_REV` must be {_P6_REV_VALUE!r} (r1 D served-tier symbol); "
        f"got {getattr(mod, 'P6_REV', None)!r}"
    )
    assert tuple(getattr(mod, "APPROVAL_MODES", ()) or ()) == APPROVAL_MODES, (
        f"`{_LEAF_MODULE}.APPROVAL_MODES` must be {APPROVAL_MODES}"
    )
    assert tuple(getattr(mod, "L4_AUTO_RISK_LEVELS", ()) or ()) == L4_AUTO_RISK_LEVELS, (
        f"`{_LEAF_MODULE}.L4_AUTO_RISK_LEVELS` must be {L4_AUTO_RISK_LEVELS} (r1.6)"
    )
    # leaf/pure-constant: must not pull DB/redis/flag/router side effects at import
    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    for banned in ("APIRouter", "include_router", "get_db", "get_redis"):
        assert banned not in src, (
            f"leaf module must stay pure (no `{banned}`); it is the served-tier probe target"
        )


# ── N: no-bypass (r1 C②) ─────────────────────────────────────────────────────

def _approval_request_sites() -> dict[str, int]:
    root = pathlib.Path(_require("app").__file__).resolve().parent
    counts: dict[str, int] = {}
    for py in root.rglob("*.py"):
        try:
            lines = py.read_text(encoding="utf-8").splitlines()
        except Exception:  # noqa: BLE001
            continue
        n = 0
        for ln in lines:
            if re.match(r"\s*class\s+ApprovalRequest\b", ln):
                continue
            if re.search(r"\bApprovalRequest\s*\(", ln):
                n += 1
        if n:
            try:
                rel = py.relative_to(root).as_posix()
            except ValueError:  # pragma: no cover
                rel = py.as_posix()
            counts[rel] = n
    return counts


def test_n1_approval_request_construction_sites_unchanged():
    """r1 C②: E6 adds ZERO `ApprovalRequest(` construction sites; the authoritative set is
    exactly 6 (exec_service x2, schedule_service x2, terminal_service x1, workflow_engine x1)."""
    got = _approval_request_sites()
    assert got == APPROVAL_REQUEST_SITES, (
        "ApprovalRequest construction sites drifted (E6 must reuse the existing chain, "
        f"adding none); expected {APPROVAL_REQUEST_SITES}, got {got}"
    )


def test_n2_exec_gate_and_dispatch_anchors_present():
    """r1 C②: named anchors for «write path must pass the approval primitive»."""
    orch = _BACKEND / "app" / "services" / "executors" / "orchestrator.py"
    appr = _BACKEND / "app" / "services" / "approval_service.py"
    assert orch.is_file(), f"missing {orch}"
    assert appr.is_file(), f"missing {appr}"
    orch_src = orch.read_text(encoding="utf-8")
    appr_src = appr.read_text(encoding="utf-8")
    assert "def _approval_gate" in orch_src, "orchestrator must define `_approval_gate` (exec entry gate)"
    assert "_approval_gate(" in orch_src, "orchestrator must CALL `_approval_gate` (cannot bypass)"
    assert "def _approve_exec" in appr_src, "approval_service must define `_approve_exec`"
    assert "def _approve_linkages" in appr_src, "approval_service must define `_approve_linkages`"
    assert "exec_dispatch.delay" in appr_src, "dispatch must go through `exec_dispatch.delay`"


def test_n3_biz_type_whitelist_unchanged():
    """r1.2 item 4 (@架构 3565 / @后端 3563): E6 adds NO `biz_type`; the authoritative set
    is exactly {exec, terminal, workflow} and rollback reuses `exec`."""
    mod = _require("app.services.approval_service")
    got = getattr(mod, "_KNOWN_BIZ_TYPES", None)
    assert got is not None, "approval_service must define `_KNOWN_BIZ_TYPES` (biz_type gate)"
    assert set(got) == {"exec", "terminal", "workflow"}, (
        "E6 must not add a biz_type (rollback reuses `exec`); expected "
        f"{{'exec','terminal','workflow'}}, got {sorted(got)}"
    )
    assert hasattr(mod, "_assert_biz_type"), "biz_type validation seam `_assert_biz_type` missing"


# ── R: flag gate order, offline (r1 B) ───────────────────────────────────────

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
    names = ("config_rule", "sys_user", "approval_request", "ai_action")
    return [tl[n] for n in names if n in tl]


@pytest.fixture()
def p6_client(tmp_path):
    """Yields ``(client, set_user, set_flag)`` for the P6 gate-order locks (offline sqlite)."""
    from app.db.base import Base  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'p6.db'}", future=True)
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


def test_r1_flag_off_is_gate_code_not_404(p6_client):
    """r1 B: flag off => running-time gate 400|403 for ANY caller (even admin), NOT 404."""
    client, set_user, set_flag = p6_client
    set_flag("ai.auto_remediate", False)
    set_user([], admin=True)
    r = client.get("/api/v1/ai/automation/circuit-breaker")
    assert r.status_code in (400, 403), (
        "feature-first: ai.auto_remediate off must gate with 400/403 (route still registered), "
        f"never 404; got {r.status_code} {r.text}"
    )


def test_r2_missing_token_is_401(p6_client):
    """r1 B: auth precedes the flag => no token gives 401."""
    client, _set_user, set_flag = p6_client
    set_flag("ai.auto_remediate", False)
    r = client.get("/api/v1/ai/automation/circuit-breaker")
    assert r.status_code == 401, (
        f"gate order: no token must be 401 (auth first); got {r.status_code} {r.text}"
    )


def test_r3_unknown_path_is_404(p6_client):
    """Sanity: a genuinely absent route is 404, so r1 is not vacuously satisfied."""
    client, set_user, set_flag = p6_client
    set_flag("ai.auto_remediate", False)
    set_user(["ai:use"], admin=True)
    r = client.get("/api/v1/ai/automation/__not_a_route__")
    assert r.status_code == 404, (
        f"unknown route must be 404 (proves the automation router is really mounted); "
        f"got {r.status_code} {r.text}"
    )
