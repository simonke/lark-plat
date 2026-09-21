# 共享库迁移白名单（migration-shared-db-allowlist）

- 权威源：后端席（owner，架构 seq2349 分工）。
- 用途：**环境-代码契约检查**——判定共享 live PG 的 `alembic_version` 是否合规。
- 边界：本清单是**权威常量源**；静态离线锁据此写常量，但**不得断言 live 的实际值**（静态锁不连 live）；live 值判定归**动态闸**。

## 迁移链（单头线性，12 版）

```
e70f471cb518 → a1c7e9d24b60 → c4f7a1d20e91 → a7b3c5d9f2e1
→ d1e2f3a4b5c6 → f5e010c0a100 → e6f7a8b9c0d1 → a1b2c3d4e5f6
→ b2c3d4e5f6a7 → d4e5f6a7b8c9 → c3d4e5f6a7b8 → e8a1b2c3d4f5
```

head = `e8a1b2c3d4f5`（唯一）。

## 允许集 / 禁止项

| 版本 | 含义 | 是否允许为 live `alembic_version` |
| --- | --- | --- |
| ≤ `d4e5f6a7b8c9` | 已落共享库（P2-MA 及更早） | 允许（已落） |
| `c3d4e5f6a7b8` | P2-3 身份接入（`auth_provider` 表 + `sys_user` 三列，**纯 add-only**） | **允许追加**（须显式放行共享库写） |
| `e8a1b2c3d4f5` | P2 close-out（`mon_alert` 去重 + 唯一索引） | **禁止**（迁移自带声明 "must NOT be applied to the shared live DB"，架构 seq2140） |

- **`ALLOWED_LIVE_REVS = {d4e5f6a7b8c9, c3d4e5f6a7b8}`**；**`e8a1b2c3d4f5 ∉ ALLOWED_LIVE_REVS`**，尽管它是代码 head。
- 允许集在链上**连续无空洞**（`d4e5f6a7b8c9 → c3d4e5f6a7b8`）；`e8a1b2c3d4f5` 为其后紧邻但**被排除**。

## 判定式

对 served HEAD 的代码：

> **code-required ≤ live `alembic_version` ≤ 允许上界（∈ `ALLOWED_LIVE_REVS`）**

- `code-required` = served HEAD 代码实际依赖的最新迁移（按链序）；例如 master `6e8c353` 含 P2-3 代码 ⇒ `code-required = c3d4e5f6a7b8`。
- **判据不是 `live == head`**：live 不应、也不允许迁到 `e8a1b2c3d4f5`。
- 本次真实漂移 = 判定式**右半失败**：代码需 P2-3（`c3d4e5f6a7b8`），live 停在 P2-MA（`d4e5f6a7b8c9`）。

## 版本合法性 ≠ 功能就绪

- **版本合法**：`live ∈ ALLOWED_LIVE_REVS`。
- **功能就绪**：代表性触库/鉴权路由**非 5xx**（如 `GET /api/v1/auth/providers`）。
- 二者**必须分开**：`d4e5f6a7b8c9` 是**合法**版本，但 P2-3 代码在其上触库路由 **500**（功能未就绪）——只能由动态闸报出。

## 静态闸 vs 动态闸

- **静态闸（离线锁，单元席）**：迁移图事实 + 本清单常量（允许集/禁止项）+ 「版本合法性 ≠ 功能就绪」注。**不连 live、不断言 live 值**。
- **动态闸（live 冒烟，当批 live 执行席，非离线席兼任）**：① `live ∈ ALLOWED_LIVE_REVS`；② `code-required ≤ live`；③ 代表触库路由 **非 5xx**。不过 ⇒ live 项 **BLOCKED**。
- 门禁纪律：区分 `httpx.HTTPError`(skip) 与 **响应 ≥500(fail/error)**；live 面「未运行」记 **NOT RUN**，不计入通过。

## 来源

- 后端 seq2338/2344/2346/2351；架构 seq2328/2349；需求 seq2326/2337/2339/2352；单元 seq2345/2347/2350；评审 seq2340/2348。
- 迁移文件：`backend/alembic/versions/{c3d4e5f6a7b8_p23_auth_provider,d4e5f6a7b8c9_p2ma_mon_alert_last_event_at,e8a1b2c3d4f5_p2_closeout_mon_alert_dedup}.py`。
