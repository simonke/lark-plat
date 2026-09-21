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

任一 **BLOCKED** ⇒ 该批 live 项即 BLOCKED，不得静默。

## 3. live 版本判据（非 `== head`）

- 权威清单＝`docs/migration-shared-db-allowlist.md`；允许集＝`{d4e5f6a7b8c9, c3d4e5f6a7b8}`；
  **`e8a1b2c3d4f5` 明令不落共享库**。
- 判据＝「**code-required ≤ live ≤ 允许上界**」（按迁移链序），**非** `== head`。
- **精确规则**：`code-required = max{ 链 ∩ B }`（B 自动同步、fail-closed）；`live` 合法性用 **A**；
  **C 版本不得入上界**（否则 `e8a1b2c3d4f5` 抬高上界使正确的 `live=c3d4e5f6a7b8` 误红——「已分类 ≠ 允许」）；
  `∃ rev ∈ 链 : rev ∉ (B∪C) ⇒ NOT RUN`（绝不低配 PASS）。
- **版本合法 ≠ 功能就绪**：`d4e5f6a7b8c9` 合法，但若 served 代码需 P2-3，则触库路由 500＝功能未就绪，
  仍须 BLOCKED。

## 4. 门禁不得把 5xx 静默转 skip

live harness 必须区分：

- `httpx.HTTPError`（连接失败）→ skip；
- **有响应且 ≥500** → **fail/error**。

`tests/integration/stage1/conftest.py` 由本批修正（`_api_reachable` / `login` / `_skip_live`，owner：后端）。

## 5. 反盲区六条（每批必守）

1. **证据面矩阵**：先列面 `单元锁` / `in-process(TestClient)` / `契约(openapi)` / `live-served` /
   `共享环境(DB/Redis/进程)`；每条验收必标所属面，触库批次至少一条落在 live-served 或共享环境。
2. **fail-closed 门禁**：禁静默转 skip——transport error＝NOT RUN、有响应 ≥5xx＝fail；NOT RUN 不计通过。
3. **环境-代码契约**：触库/迁移批次必查「code-required ≤ live `alembic_version` ≤ 允许上界」＋代表触库路由非 5xx。
4. **防同质（common-mode）**：各席若验同一面＝0 冗余；至少一席走不同面，或显式声明「只验了 X、未验 Y」；
   禁把各自同面全绿当组合绿。
5. **非空判/负控制**：每个门禁须证明能变红（前置 SHA/真实漂移即 RED/BLOCKED）；未证明能红＝门禁不成立。
6. **措辞纪律**：live 结论必附 PID/served HEAD/DB revision；未做 e2e/真机不得称「功能全绿」；
   live 项显式「已验（附证据）/列 C」，禁隐式。

配套：`docs/acceptance-checklist-template.md`（每批填写，含「本批未覆盖面」必填栏）。

## 6. 判据侧细化（@需求 seq2366）

1. **清单开场冻结**：每批**开场**即冻结「证据面矩阵＋每面判据」；「本批未覆盖面」由**需求席**登记为
   limit／列 C；收口**不得删项、不得事后追认**。
2. **证方 ≠ 产方**（反共模硬判据）：某面的 producer **不得**同时提供该面的 acceptance 证据；
   至少一个被接受要件的证据来自**不同席/不同面**。
3. **负控制为预核要件**：凡门禁须**演示过能变红**，未演示⇒预核**不予绑定**。
4. **环境实例身份**：`live-served` 附 **PID＋served HEAD**；`共享环境` 附 **DB revision＋实例标识（端口/库名）**。
5. **NOT RUN／未覆盖面统一入账本列 C**（需求席登记）；收口报告**必须引用**；「未验即不称改」为硬约束。
