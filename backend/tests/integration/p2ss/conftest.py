"""Offline API-level harness for the P2-SS executor endpoints.

Boots the *real* FastAPI app in-process, with three overrides so nothing
external is touched (no shared PostgreSQL, no Redis, no login):

  * ``get_db``            -> a temp file SQLite session (JSONB compiled to JSON);
  * ``SessionLocal``      -> rebound to that SQLite engine, so the audit
                             middleware writes offline as well;
  * ``get_current_user``  -> a fake ``CurrentUser`` (permission toggled per test,
                             which is how the 403 path is exercised).

The app is used without its lifespan context manager, so ``run_seed``/Redis are
never started. This module is the integration-side authoring copy for
``p2-ss-executor``; it is meant to be committed add-only on top of the backend
branch once that branch has a clean SHA.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# --- make the lark-plat backend importable --------------------------------
# Resolution order: explicit env override -> committed repo layout
# (<repo>/backend/tests/integration/p2ss/conftest.py => parents[2] == backend)
# -> this authoring seat's checkout.
_HERE = Path(__file__).resolve().parent
_DEV_BACKEND = r"C:\Users\youth\.loop\agents\agt_dp9sj7cgogb0l2\lark-plat\backend"

# The commit-ready mirror under ./commit duplicates these test basenames; keep it
# out of this directory's collection (pytest default import mode has no package).
collect_ignore_glob = ["commit/*"]


def _resolve_backend() -> Path:
    env = os.environ.get("LARK_BACKEND")
    if env:
        return Path(env)
    cand = _HERE.parents[2]
    if (cand / "app" / "main.py").is_file():
        return cand
    return Path(_DEV_BACKEND)


_BACKEND = _resolve_backend()
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402
from sqlalchemy import BigInteger, create_engine  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

import app.db.models  # noqa: E402,F401  (register all tables on Base.metadata)
import app.db.session as _dbs  # noqa: E402
from app.db.base import Base  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_as_json(type_, compiler, **kw):  # noqa: ANN001
    return "JSON"


@compiles(BigInteger, "sqlite")
def _bigint_as_integer(type_, compiler, **kw):  # noqa: ANN001
    # SQLite only autoincrements a column typed exactly INTEGER; the models use
    # BigInteger PKs, whose DDL would otherwise be NOT NULL with no rowid alias.
    return "INTEGER"


_PUBLIC_PERMS = {"asset:host:list", "asset:host:edit", "asset:host:conn"}


def _needed_tables():
    """Only the tables the asset endpoints + audit middleware actually touch.

    Full ``Base.metadata`` cannot be created on SQLite (e.g. ``exec_log`` has a
    composite autoincrement PK that SQLite rejects), so create the minimal set.
    """
    from app.db.models import AssetGroup, AuditLog, ConfigRule, Host, HostCredential

    return [
        AssetGroup.__table__,
        Host.__table__,
        HostCredential.__table__,
        ConfigRule.__table__,
        AuditLog.__table__,
    ]


@pytest.fixture()
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'p2ss.db'}", future=True)
    Base.metadata.create_all(engine, tables=_needed_tables())
    return engine


@pytest.fixture()
def session(sqlite_engine):
    maker = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False, future=True)
    s = maker()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def app_client(sqlite_engine, session):
    """Yields (client, set_user, seed_host). ``set_user(perms, admin=False)``."""
    _dbs.SessionLocal.configure(bind=sqlite_engine)

    import app.main as main
    from app.api.deps import CurrentUser, get_current_user
    from app.db.session import get_db
    from starlette.testclient import TestClient

    def _get_db():
        yield session

    main.app.dependency_overrides[get_db] = _get_db

    def set_user(perms=None, admin=False):
        user = CurrentUser(
            user_id=1,
            username="qa",
            is_admin=admin,
            permissions=list(_PUBLIC_PERMS if perms is None else perms),
            visible_group_ids=[1],
        )
        main.app.dependency_overrides[get_current_user] = lambda: user
        return user

    def seed_host(host_id=1, *, connector="agent", group_id=1, **extra):
        from app.db.models import AssetGroup, Host

        if session.get(AssetGroup, group_id) is None:
            session.add(AssetGroup(id=group_id, parent_id=0, name=f"g{group_id}"))
            session.flush()
        host = Host(
            id=host_id,
            hostname=extra.pop("hostname", f"host{host_id}"),
            ip=extra.pop("ip", f"10.0.0.{host_id}"),
            group_id=group_id,
            connector=connector,
            **extra,
        )
        session.add(host)
        session.commit()
        return host_id

    set_user()
    try:
        yield TestClient(main.app), set_user, seed_host
    finally:
        main.app.dependency_overrides.clear()


# --- exec/SS-5 extension: exec tables + offline broker/redis stand-ins -----

# ``exec_log`` has a composite autoincrement PK (id + created_at) that SQLite
# refuses to build via ``Base.metadata``; create an equivalent sqlite table
# (id autoincrement + created_at server default) directly. The ORM only cares
# about columns on INSERT/SELECT, so the differing PK declaration is harmless.
_EXEC_LOG_DDL = (
    "CREATE TABLE IF NOT EXISTS exec_log ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " task_host_id BIGINT NOT NULL,"
    " seq INTEGER NOT NULL,"
    " level VARCHAR(16),"
    " content TEXT NOT NULL,"
    " created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
    " UNIQUE (created_at, task_host_id, seq))"
)


def _exec_tables():
    from app.db.models import ApprovalRequest, ExecTask, ExecTaskHost, Script

    return [
        Script.__table__,
        ExecTask.__table__,
        ExecTaskHost.__table__,
        ApprovalRequest.__table__,
    ]


@pytest.fixture()
def exec_env(app_client, sqlite_engine, session, monkeypatch):
    """``app_client`` plus the exec tables, with Redis/celery broker stubbed.

    Offline by construction: ``get_redis`` returns ``None`` (semaphores degrade
    to no-ops, no shared Redis touched) and the celery broker is replaced by an
    in-process shim so ``.delay`` runs the real ``exec_dispatch``.
    """
    from sqlalchemy import text as _text

    import app.tasks.exec_tasks as exec_tasks

    Base.metadata.create_all(sqlite_engine, tables=_exec_tables())
    with sqlite_engine.begin() as conn:
        conn.execute(_text(_EXEC_LOG_DDL))

    import app.core.redis_helper as redis_helper

    monkeypatch.setattr(redis_helper, "get_redis", lambda: None)

    from app.services import exec_service

    monkeypatch.setattr(exec_service, "_task_no", lambda db: "T-TEST-0001")

    class _Broker:
        def __call__(self, task_id):
            return exec_tasks.exec_dispatch(task_id)

        def delay(self, task_id, **_kw):
            return exec_tasks.exec_dispatch(task_id)

    monkeypatch.setattr(exec_service, "exec_dispatch", _Broker())

    client, set_user, seed_host = app_client
    return {
        "client": client,
        "set_user": set_user,
        "seed_host": seed_host,
        "session": session,
        "exec_tasks": exec_tasks,
        "exec_service": exec_service,
    }
