"""Stage-1 integration seed manager: ensure / clean the WS-token exec-task seed.

Why this exists
---------------
`test_ws_token::test_e1_owner_gets_token` needs an exec task **owned by the
`operator` seed user** with at least one `exec_task_host`, because the backend
enforces task ownership for non-admins (`exec_service.ws_token`: non-admin must
match `created_by`). Without it E1 used to skip ("no exec tasks seeded"), which
was the last non-green in the stage-1 live suite (架构 seq2140 item4:
`test_ws_token` 消 skip).

This tool is idempotent and reversible:
    --ensure   create the operator-owned seed task if absent (default)
    --clean    delete the seed task (exec_task_host/exec_log cascade), keeping
               the DB free of integration debris — the "阶段1 种子清理" half
    --status   print whether the seed exists

Run from the backend venv:
    python backend/tests/integration/stage1/tools/stage1_seed.py --ensure
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
    """Best-effort: load backend/.env so the tool works from any cwd."""
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

from sqlalchemy import select, text  # noqa: E402

from app.db.models.exec import ExecTask, ExecTaskHost  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

SEED_TASK_NO = "IT-WS-SEED-001"
SEED_TASK_NAME = "it-ws-seed"


def _operator(db):
    # raw SQL: the live DB may predate the P2-ID sys_user.auth_source column, so a
    # full ORM User select would fail; we only need the operator id.
    return db.execute(
        text("select id from sys_user where username = 'operator'")
    ).first()


def _host_a1(db):
    return db.execute(
        text("select id, hostname, ip from asset_host where hostname = 'hostA1'")
    ).first()


def ensure() -> int:
    db = SessionLocal()
    try:
        op = _operator(db)
        if op is None:
            print("ERROR: seed user 'operator' not found (run app.db.seed first)")
            return 1
        host = _host_a1(db)
        if host is None:
            print("ERROR: seed host 'hostA1' not found (stage-1 seed missing)")
            return 1
        existing = db.scalar(select(ExecTask).where(ExecTask.task_no == SEED_TASK_NO))
        if existing is not None:
            print(f"seed exists: task id={existing.id} task_no={existing.task_no}")
            return 0
        task = ExecTask(
            task_no=SEED_TASK_NO,
            name=SEED_TASK_NAME,
            kind="command",
            command="echo it-ws-seed",
            target_host_ids={"ids": [host.id]},
            mode="batch",
            status="success",
            created_by=op.id,
        )
        db.add(task)
        db.flush()
        db.add(
            ExecTaskHost(
                exec_task_id=task.id,
                host_id=host.id,
                hostname=host.hostname,
                ip=host.ip or "127.0.0.1",
                executor="agent",
                status="success",
            )
        )
        db.commit()
        print(f"seed created: task id={task.id} task_no={SEED_TASK_NO} owner=operator({op.id})")
        return 0
    finally:
        db.close()


def clean() -> int:
    db = SessionLocal()
    try:
        rows = db.execute(
            text("select id from exec_task where task_no = :no"), {"no": SEED_TASK_NO}
        ).all()
        if not rows:
            print("seed absent; nothing to clean")
            return 0
        # FK ondelete=CASCADE covers exec_task_host -> exec_log.
        db.execute(text("delete from exec_task where task_no = :no"), {"no": SEED_TASK_NO})
        db.commit()
        print(f"seed cleaned: removed task_no={SEED_TASK_NO} (+exec_task_host/exec_log cascade)")
        return 0
    finally:
        db.close()


def status() -> int:
    db = SessionLocal()
    try:
        task = db.scalar(select(ExecTask).where(ExecTask.task_no == SEED_TASK_NO))
        if task is None:
            print("seed absent")
            return 1
        n = db.execute(
            text("select count(*) from exec_task_host where exec_task_id = :tid"),
            {"tid": task.id},
        ).scalar()
        print(f"seed present: task id={task.id} owner={task.created_by} hosts={n}")
        return 0
    finally:
        db.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--ensure", action="store_true", help="create the seed if absent (default)")
    g.add_argument("--clean", action="store_true", help="delete the seed task")
    g.add_argument("--status", action="store_true", help="report seed presence")
    args = ap.parse_args()
    if args.clean:
        return clean()
    if args.status:
        return status()
    return ensure()


if __name__ == "__main__":
    raise SystemExit(main())
