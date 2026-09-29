"""Cold-start robustness contract (fresh-volume multi-worker seed race).

Regression guard for the `:8012` first-boot incident: `uvicorn --workers 2`
runs lifespan in both workers, so `run_seed` races on the unique permission
index (``ix_sys_permission_code``) and the loser aborts startup.

Two invariants (both DB-free / deterministic):
  1. `run_seed` takes a PostgreSQL transaction-scoped advisory lock so seeding
     is single-writer (and is a no-op on non-PostgreSQL dialects, e.g. tests).
  2. `app.main.lifespan` rolls the session back on a seed failure, so the shared
     session does not stay "pending rollback" and kill `resolve_store_config`.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

from app.db.seed import _SEED_LOCK_KEY, _acquire_seed_lock, run_seed


def test_run_seed_acquires_seed_lock_before_writing():
    """run_seed must serialize on the advisory lock before touching the DB."""
    src = inspect.getsource(run_seed)
    assert "_acquire_seed_lock(db)" in src, "run_seed must take the seed lock"


def test_seed_lock_uses_pg_advisory_xact_lock():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "postgresql"
    _acquire_seed_lock(db)
    assert db.execute.called, "postgresql must issue the advisory lock"
    (stmt, params), _ = db.execute.call_args
    assert "pg_advisory_xact_lock" in str(stmt)
    assert params == {"key": _SEED_LOCK_KEY}


def test_seed_lock_is_noop_on_non_postgresql():
    db = MagicMock()
    db.get_bind.return_value.dialect.name = "sqlite"
    _acquire_seed_lock(db)
    db.execute.assert_not_called()


def test_lifespan_rolls_back_failed_seed():
    """The seed `except` must clear the failed tx before resolve_store_config."""
    from app import main

    src = inspect.getsource(main.lifespan)
    except_idx = src.index("run_seed(db)")
    rollback_idx = src.index("db.rollback()", except_idx)
    store_idx = src.index("resolve_store_config(db)", except_idx)
    assert except_idx < rollback_idx < store_idx, (
        "lifespan must call db.rollback() after a failed run_seed and before "
        "resolve_store_config(db)"
    )
