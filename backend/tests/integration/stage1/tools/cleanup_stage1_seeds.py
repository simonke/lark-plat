"""Stage-1 seed cleanup: remove accumulated non-baseline **test hosts** from the
shared live DB so the stage-1 data-scope environment matches its intended seed.

Background
----------
`test_datascope::c2` went red because the shared live DB accumulated ~53
`e2e-*`/`repro-*`/`us8-*`/`probe*` hosts in group A from earlier e2e suites
(架构 seq2127 §三 "种子清理"; 需求 seq2130). The c2 fixture was made immune via
dynamic derivation, but the environment itself should still be reset to the
frozen stage-1 seed:

    groupA: hostA1, hostA2      groupB: hostB1

This tool is **dry-run by default**. It only touches hosts whose hostname matches
a test pattern and is not one of the three baseline hosts. Dependents without a
DB-level FK (exec_task_host.host_id) are deleted first; terminal_session and
host_credential cascade, transfer_host is deleted explicitly.

Run from the backend venv:
    python backend/tests/integration/stage1/tools/cleanup_stage1_seeds.py            # dry-run
    python backend/tests/integration/stage1/tools/cleanup_stage1_seeds.py --apply    # execute
DATABASE_URL is read from the environment or from backend/.env.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[4]
sys.path.insert(0, str(_BACKEND))


def _load_backend_env() -> None:
    if os.environ.get("DATABASE_URL"):
        return
    env = _BACKEND / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_backend_env()

from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402

TEST_PATTERN = (
    "(hostname like 'e2e-%' or hostname like 'repro%' or hostname like 'us8-%' "
    "or hostname like 'probe%' or hostname like 'it-%' or hostname like 's4-%')"
)
BASELINE = ("hostA1", "hostA2", "hostB1")


def _targets(db) -> list[int]:
    rows = db.execute(
        text(
            f"select id from asset_host where {TEST_PATTERN} "
            f"and hostname not in :base order by id"
        ).bindparams(base=BASELINE)
    ).all()
    return [r[0] for r in rows]


def _count(db, sql: str, ids: list[int]) -> int:
    if not ids:
        return 0
    return int(db.execute(text(sql).bindparams(ids=ids)).scalar() or 0)


def _report(db) -> list[int]:
    ids = _targets(db)
    print(f"baseline hosts: {BASELINE}")
    print(f"non-baseline test hosts to remove: {len(ids)} -> {ids}")
    for label, sql in (
        ("exec_task_host (no FK)", "select count(*) from exec_task_host where host_id = any(:ids)"),
        ("terminal_session (cascade chunks)", "select count(*) from terminal_session where host_id = any(:ids)"),
        ("host_credential (cascade)", "select count(*) from host_credential where host_id = any(:ids)"),
        ("transfer_host", "select count(*) from transfer_host where host_id = any(:ids)"),
    ):
        print(f"  dependent {label}: {_count(db, sql, ids)}")
    total = int(db.execute(text("select count(*) from asset_host")).scalar() or 0)
    print(f"asset_host total now: {total}")
    return ids


def apply() -> int:
    db = SessionLocal()
    try:
        ids = _targets(db)
        if not ids:
            print("no non-baseline test hosts; nothing to clean")
            return 0
        # delete dependents first (exec_task_host.host_id has no DB FK)
        db.execute(text("delete from exec_task_host where host_id = any(:ids)"), {"ids": ids})
        db.execute(text("delete from transfer_host where host_id = any(:ids)"), {"ids": ids})
        db.execute(text("delete from host_credential where host_id = any(:ids)"), {"ids": ids})
        db.execute(text("delete from terminal_session where host_id = any(:ids)"), {"ids": ids})
        db.execute(text("delete from asset_host where id = any(:ids)"), {"ids": ids})
        db.commit()
        remaining = int(db.execute(text("select count(*) from asset_host")).scalar() or 0)
        print(f"cleaned {len(ids)} test hosts; asset_host total now: {remaining}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="execute the deletion (default: dry-run)")
    args = ap.parse_args()
    if args.apply:
        return apply()
    db = SessionLocal()
    try:
        _report(db)
        print("\n(dry-run) re-run with --apply to execute")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
