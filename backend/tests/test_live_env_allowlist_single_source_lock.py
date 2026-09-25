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
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = BACKEND_DIR.parent
_SMOKE_PATH = BACKEND_DIR / "tools" / "live_readiness_smoke.py"
_LOCK_PATH = BACKEND_DIR / "tests" / "test_live_env_contract_lock.py"
_DOCS_PATH = _REPO_ROOT / "docs" / "migration-shared-db-allowlist.md"


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
    expected = {lock.CLOSEOUT_REV, lock.P3_REV, lock.P3X_REV, lock.P3_3_REV, lock.P3_4_REV}
    assert lock.MIGRATION_LIVE_FORBIDDEN == expected, (
        f"C must be exactly {{{lock.CLOSEOUT_REV}, {lock.P3_REV}, {lock.P3X_REV}, "
        f"{lock.P3_3_REV}, {lock.P3_4_REV}}}; "
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
