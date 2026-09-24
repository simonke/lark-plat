# P2-SS executor-extension integration harness (offline)

Self-contained, **offline** integration tests for the P2-SS executor endpoints
and the ssh execution route. Committed add-only under
`backend/tests/integration/p2ss/` (mirrors the `stage1/` layout). Because
`backend/pyproject.toml` sets `norecursedirs = ["tests/integration", ...]`, a
plain `pytest` run does **not** collect this subtree — run it explicitly.

## Run

```powershell
# from backend/, backend venv active
pytest tests/integration/p2ss
```

The harness boots the **real** FastAPI app in-process and overrides three
boundaries so nothing external is touched (no shared PostgreSQL, no Redis, no
login):

* `get_db` -> a temp-file SQLite session (JSONB -> JSON, BigInteger -> INTEGER);
* `SessionLocal` -> rebound to that SQLite engine (audit middleware writes offline);
* `get_current_user` -> a fake `CurrentUser` (permissions toggled per test).

The app is used **without** its lifespan context manager, so `run_seed`/Redis
never start. `exec_env` additionally stubs `get_redis` -> `None` (semaphores
degrade to no-ops) and the celery broker (`.delay` runs the real
`exec_dispatch` in-process).

## Coverage

* SS-2 add-only contract: `GET .../executors`, `PUT .../connector`;
  `docs/openapi.json` paths == 109, `/monitor*` == 19.
* SS-3 permission + zero credential echo; US-03 cross-group 403.
* SS-4 connector switch persists; invalid value -> 422.
* SS-5 route reachability (**create path only**) + gate order
  `approval -> sensitivity -> exec -> exec_log`.

## Scope / limitations (registered, not omissions)

* Skeleton only: **no real SSH**. `paramiko` (D: drive install), the Windows
  `agent.exe` build and real-host联调 are deferred to the release phase.
* The **approval-resume** dispatch path (`approval_service` `exec_dispatch.delay`
  inside `try/except: pass`) is **not** reachable offline (broker absent) and is
  therefore deferred ("C"), not used as route evidence.
