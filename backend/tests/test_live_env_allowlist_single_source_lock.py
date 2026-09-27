"""Lock (W2): the A/B/C shared-DB allow-list literals do not drift across code homes.

Context (arch seq2567-5 / req seq2566-5): the three allow-list sets currently live in
two code homes and are re-stated in docs:

- runtime gate : ``backend/tools/live_readiness_smoke.py``  (L31/L33/L39)
- static lock  : ``backend/tests/test_live_env_contract_lock.py``  (L35/L36/L49)
- docs         : ``docs/migration-shared-db-allowlist.md``

They are byte-consistent today, but nothing links the two code declarations, so a
future chain change can update one and silently drift the other. This lock keeps both
declarations (the static lock stays an *independent recomputation*, not an import of
the gate) and asserts they are identical, turning "single source" from a convention
into a red-able assertion.

Negative control (manual, one-off; record as evidence, do not commit the mutation):
    temporarily change any member of ``LIVE_REV_ALLOWED`` / ``MIGRATION_LIVE_*`` in
    either file -> the two corresponding tests below MUST go red. If they stay green
    the lock is not actually linking the two homes.

A = LIVE_REV_ALLOWED (allowed dwell), B = MIGRATION_LIVE_APPLICABLE, C = MIGRATION_LIVE_FORBIDDEN.

Run (from the backend checkout, backend venv):
    python -m pytest tests/test_live_env_allowlist_single_source_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = BACKEND_DIR.parent
_SMOKE_PATH = BACKEND_DIR / "tools" / "live_readiness_smoke.py"
_LOCK_PATH = BACKEND_DIR / "tests" / "test_live_env_contract_lock.py"
_DOCS_PATH = _REPO_ROOT / "docs" / "migration-shared-db-allowlist.md"

# Named governance exception register (Tier1, policy-常驻): rev ∈ C that is already resident on
# the shared dev DB and is an ancestor of the repo head, so it may dwell there. This is a
# deliberate, bounded exception — NOT a general allow-list widening; the smoke gate's
# `LIVE_REV_DWELL_OVERRIDE` (an INDEPENDENT declaration, no import of this lock) must equal
# `frozenset(LIVE_REV_DWELL_REGISTER)`.
#
# Carrier split (arch seq3694③ / seq3710): Tier1 = THIS register (in-repo, policy-resident,
# exercised on every CI run); Tier2 = a periodic ops/CI runner of live_readiness_smoke.py, which
# is the only thing that can surface *runtime* drift continuously. The policy owner did NOT name a
# Tier2 runner, so it is registered here as an explicit GAP: runtime drift is "visible when the
# gate is run", NOT continuously. docs/migration-shared-db-allowlist.md is intentionally
# unchanged (f5a6b7c8d9e0 already classified ∈ C, row 19).
LIVE_REV_DWELL_REGISTER = {
    "f5a6b7c8d9e0": {"first_resident": "M10", "in_C": True, "disjoint_A": True},
}

# Isolated-subprocess probe: loads the runtime gate, computes the real migration order, and calls
# the pure classifier `_classify_db_rev` with an injected `live`/`required` (DB-free). Prints one
# JSON line {verdict, detail}. The probe proves the RUN-TIME output shape (token present/absent),
# which a static constant assertion cannot.
_PROBE_SCRIPT = r"""
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("_smoke_probe", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
order = mod._migration_order(mod._repo_root(None) / "backend" / "alembic" / "versions")
verdict, detail = mod._classify_db_rev(sys.argv[2], order=order, required=sys.argv[3])
print(json.dumps({"verdict": verdict, "detail": detail}))
"""


def _probe_classify(live: str, required: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE_SCRIPT, str(_SMOKE_PATH), live, required],
        capture_output=True, text=True, cwd=str(BACKEND_DIR), timeout=120,
    )
    assert proc.returncode == 0, f"probe failed: {proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _smoke():
    return _load("_live_readiness_smoke_under_test", _SMOKE_PATH)


def _lock():
    return _load("_live_env_contract_lock_under_test", _LOCK_PATH)


def test_w2_smoke_and_lock_declare_identical_allowlist_sets():
    smoke = _smoke()
    lock = _lock()
    assert smoke.LIVE_REV_ALLOWED == lock.LIVE_REV_ALLOWED, (
        "A LIVE_REV_ALLOWED drifted between live_readiness_smoke.py and the static lock: "
        f"smoke={sorted(smoke.LIVE_REV_ALLOWED)} lock={sorted(lock.LIVE_REV_ALLOWED)}"
    )
    assert smoke.MIGRATION_LIVE_APPLICABLE == lock.MIGRATION_LIVE_APPLICABLE, (
        "B MIGRATION_LIVE_APPLICABLE drifted between live_readiness_smoke.py and the static lock: "
        f"only-in-smoke={sorted(smoke.MIGRATION_LIVE_APPLICABLE - lock.MIGRATION_LIVE_APPLICABLE)}, "
        f"only-in-lock={sorted(lock.MIGRATION_LIVE_APPLICABLE - smoke.MIGRATION_LIVE_APPLICABLE)}"
    )
    assert smoke.MIGRATION_LIVE_FORBIDDEN == lock.MIGRATION_LIVE_FORBIDDEN, (
        "C MIGRATION_LIVE_FORBIDDEN drifted between live_readiness_smoke.py and the static lock: "
        f"smoke={sorted(smoke.MIGRATION_LIVE_FORBIDDEN)} lock={sorted(lock.MIGRATION_LIVE_FORBIDDEN)}"
    )


def test_w2_closeout_rev_is_sole_forbidden_member_in_both_homes():
    smoke = _smoke()
    lock = _lock()
    expected = {
        lock.CLOSEOUT_REV, lock.P3_REV, lock.P3X_REV, lock.P3_3_REV, lock.P3_4_REV,
        lock.P3_5_REV, lock.P4_REV, lock.P5_REV, lock.P6_REV,
    }
    assert lock.MIGRATION_LIVE_FORBIDDEN == expected, (
        f"C must be exactly {{{lock.CLOSEOUT_REV}, {lock.P3_REV}, {lock.P3X_REV}, "
        f"{lock.P3_3_REV}, {lock.P3_4_REV}, {lock.P3_5_REV}, {lock.P4_REV}, {lock.P5_REV}, "
        f"{lock.P6_REV}}}; "
        f"got {sorted(lock.MIGRATION_LIVE_FORBIDDEN)}"
    )
    assert smoke.MIGRATION_LIVE_FORBIDDEN == expected, (
        "smoke C must be the same exact forbidden set as the static lock; "
        f"got {sorted(smoke.MIGRATION_LIVE_FORBIDDEN)}"
    )


def test_w2_allowlist_docs_reference_every_classified_rev():
    lock = _lock()
    assert _DOCS_PATH.is_file(), f"allow-list docs missing: {_DOCS_PATH}"
    text = _DOCS_PATH.read_text(encoding="utf-8", errors="ignore")
    missing = sorted(
        rev for rev in (lock.MIGRATION_LIVE_APPLICABLE | lock.MIGRATION_LIVE_FORBIDDEN)
        if rev not in text
    )
    assert not missing, (
        f"docs/migration-shared-db-allowlist.md is out of sync; unlisted rev(s): {missing}"
    )


# ── W3: dwell-override (A2) governance exception ───────────────────────────────
# Negative control (manual, one-off; record as evidence, do not commit the mutation):
#   remove any member from LIVE_REV_DWELL_REGISTER (or the smoke override) -> the equality /
#   boundedness test below MUST go red; change the smoke classifier to drop the `and not dwell`
#   exemption -> the dwell-pass probe MUST go red; let the override swallow `code-required <= live`
#   -> the `code-required above dwell` probe MUST go red.

def test_w3_dwell_override_matches_register_and_is_bounded():
    smoke = _smoke()
    assert smoke.LIVE_REV_DWELL_OVERRIDE == frozenset(LIVE_REV_DWELL_REGISTER), (
        "LIVE_REV_DWELL_OVERRIDE (smoke) must equal LIVE_REV_DWELL_REGISTER keys (lock): "
        f"smoke={sorted(smoke.LIVE_REV_DWELL_OVERRIDE)} lock={sorted(LIVE_REV_DWELL_REGISTER)}"
    )
    assert LIVE_REV_DWELL_REGISTER, "dwell register must be a named, non-empty exception"
    for rev, meta in LIVE_REV_DWELL_REGISTER.items():
        assert rev in smoke.MIGRATION_LIVE_FORBIDDEN, (
            f"dwell member {rev} must be a C (forbidden) member (D ⊆ C)"
        )
        assert rev not in smoke.LIVE_REV_ALLOWED, (
            f"dwell member {rev} must NOT be in A LIVE_REV_ALLOWED (D ∩ A = ∅)"
        )
        assert meta.get("in_C") is True, f"{rev}: in_C must be True"
        assert meta.get("disjoint_A") is True, f"{rev}: disjoint_A must be True"
        assert meta.get("first_resident"), f"{rev}: first_resident must be set (pre-batch residency)"
    assert set(LIVE_REV_DWELL_REGISTER) & smoke.LIVE_REV_ALLOWED == set(), (
        "dwell register must be disjoint from A LIVE_REV_ALLOWED"
    )


def test_w3_smoke_declares_override_independently_of_lock():
    src = _SMOKE_PATH.read_text(encoding="utf-8")
    assert "test_live_env_contract_lock" not in src, "smoke must not import the static lock"
    assert "test_live_env_allowlist_single_source_lock" not in src, (
        "smoke must not import the single-source lock (must stay an independent recomputation)"
    )
    assert "LIVE_REV_DWELL_REGISTER" not in src, (
        "smoke must declare LIVE_REV_DWELL_OVERRIDE independently, not reference the lock register"
    )


def test_w3_probe_dwell_pass_emits_token():
    r = _probe_classify("f5a6b7c8d9e0", "c3d4e5f6a7b8")
    assert r["verdict"] == "PASS", r
    assert "dwell-exception=f5a6b7c8d9e0" in r["detail"], r


def test_w3_probe_other_c_member_is_blocked():
    r = _probe_classify("e8a1b2c3d4f5", "c3d4e5f6a7b8")
    assert r["verdict"] == "BLOCKED", r


def test_w3_probe_code_required_above_dwell_still_blocked():
    # proves the override does NOT swallow the `code-required <= live` guard
    r = _probe_classify("f5a6b7c8d9e0", "P6_REV")
    assert r["verdict"] == "BLOCKED", r


def test_w3_probe_plain_pass_has_no_dwell_token():
    r = _probe_classify("c3d4e5f6a7b8", "c3d4e5f6a7b8")
    assert r["verdict"] == "PASS", r
    assert "dwell-exception" not in r["detail"], r
