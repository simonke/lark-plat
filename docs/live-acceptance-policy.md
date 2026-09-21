# Live 验收与证据面纪律（env-gates 批）

本批修复 P2-SS 收口时暴露的**跨面盲区**：五席证据同处离线/in-process 面，长期未发现共享
live DB 停在 `d4e5f6a7b8c9`（pre-P2-3）导致 `/auth/*` 全线 500。以下条款随批生效。

## 1. 证据面必须显式标注

每条验收/签核必须标注证据面，禁止隐式：

- `in-process`：`TestClient` / 迁移进程内自建 schema / 离线锁——**不得**据此声称 live 通过。
- `live`：真实 served 进程 + 共享 PG。**live 结论必须附**：PID、served HEAD、live DB `alembic_version`。

live 未运行＝**NOT RUN**，不计入「通过」（列 C 显式登记）。

## 2. live 就绪冒烟（每批开场＋收口各一次）

owner＝**当批 live 执行席**（不得由离线测试席兼任）。闸门见 `backend/tools/live_readiness_smoke.py`：

1. **contract**：live `/openapi.json` 与 served 树 `docs/openapi.json` JSON 逐键相等；
2. **db_rev**：`SELECT version_num FROM alembic_version` ∈ 允许集 **且** `code-required ≤ live ≤ 允许上界`；
3. **db_touch**：代表触库路由（`/auth/providers`）**非 5xx**。

任一 FAIL ⇒ 该批 live 项 **BLOCKED**，不得静默。

## 3. live 版本判据（非 `== head`）

- 权威清单＝`docs/migration-shared-db-allowlist.md`；允许集＝`{d4e5f6a7b8c9, c3d4e5f6a7b8}`；
  **`e8a1b2c3d4f5` 明令不落共享库**。
- 判据＝「**code-required ≤ live ≤ 允许上界**」（按迁移链序），**非** `== head`。
- **版本合法 ≠ 功能就绪**：`d4e5f6a7b8c9` 合法，但若 served 代码需 P2-3，则触库路由 500＝功能未就绪，
  仍须 BLOCKED。

## 4. 门禁不得把 5xx 静默转 skip

live harness 必须区分：

- `httpx.HTTPError`（连接失败）→ skip；
- **有响应且 ≥500** → **fail/error**。

`tests/integration/stage1/conftest.py` 由本批修正（`_api_reachable` / `login` / `_skip_live`，owner：后端）。
