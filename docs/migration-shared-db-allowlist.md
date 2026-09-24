# 共享库迁移白名单（migration-shared-db-allowlist）

- 权威源：后端席（owner，架构 seq2349 分工；三集合命名与不变式经架构 seq2371 裁定、需求 seq2370 精确化）。
- 用途：**环境-代码契约检查**——判定共享 live PG 的 `alembic_version` 是否合规，并为 `code-required` 推导提供已分类上界。
- 边界：本清单是**权威常量源**；静态离线锁据此写常量，但**不得断言 live 的实际值**（静态锁不连 live）；live 值判定归**动态闸**（`backend/tools/live_readiness_smoke.py`）。

## 迁移链（单头线性，15 版）

```
e70f471cb518 → a1c7e9d24b60 → c4f7a1d20e91 → a7b3c5d9f2e1
→ d1e2f3a4b5c6 → f5e010c0a100 → e6f7a8b9c0d1 → a1b2c3d4e5f6
→ b2c3d4e5f6a7 → d4e5f6a7b8c9 → c3d4e5f6a7b8 → e8a1b2c3d4f5 → c9e3f1a2b4d6
→ e1f2a3b4c5d7 → f2a3b4c5d6e7
```

head = `f2a3b4c5d6e7`（唯一；P3.3 CMDB 深化 `entity_relation` 关系/拓扑/影响分析）。

## 三集合（A / B / C；命名固定，禁互换）

| 集合 | 常量名 | 语义 | 值 |
| --- | --- | --- | --- |
| **A** | `LIVE_REV_ALLOWED` | live `alembic_version` **允许停留值**（**live 合法性**判据） | `{d4e5f6a7b8c9, c3d4e5f6a7b8}` |
| **B** | `MIGRATION_LIVE_APPLICABLE` | **可被应用**到共享库的迁移全集 | 11 版（链上 ≤ `c3d4e5f6a7b8`） |
| **C** | `MIGRATION_LIVE_FORBIDDEN` | **禁落**共享库的迁移 | `{e8a1b2c3d4f5, c9e3f1a2b4d6, e1f2a3b4c5d7, f2a3b4c5d6e7}` |

> ⚠️ **A ≠ B**：A 是「当前可停留的最高两版」，B 是「可被应用的迁移全集」。**不可互换**。

## 全 15 版显式分类

| # | 版本 | 迁移 | ∈B 可落 | ∈A 可停留 | ∈C 禁落 |
| --- | --- | --- | --- | --- | --- |
| 1 | `e70f471cb518` | initial schema | ✓ | | |
| 2 | `a1c7e9d24b60` | stage2 asset contract alignment | ✓ | | |
| 3 | `c4f7a1d20e91` | stage4 web terminal | ✓ | | |
| 4 | `a7b3c5d9f2e1` | widen terminal session status | ✓ | | |
| 5 | `d1e2f3a4b5c6` | sequence-backed no generation | ✓ | | |
| 6 | `f5e010c0a100` | partition exec_log by month | ✓ | | |
| 7 | `e6f7a8b9c0d1` | P2-MA monitor tables | ✓ | | |
| 8 | `a1b2c3d4e5f6` | mon rule scope level converge | ✓ | | |
| 9 | `b2c3d4e5f6a7` | P2-1 transfer tables | ✓ | | |
| 10 | `d4e5f6a7b8c9` | P2-MA mon_alert last_event_at | ✓ | ✓（已落） | |
| 11 | `c3d4e5f6a7b8` | P2-3 auth provider（add-only） | ✓ | ✓（可追加，须放行） | |
| 12 | `e8a1b2c3d4f5` | P2 close-out mon_alert dedup | | | ✓（"must NOT be applied to the shared live DB"，架构 seq2140） |
| 13 | `c9e3f1a2b4d6` | P3-1/P3-2 ticket + kb | | | ✓（descends from the close-out ⇒ 不可落共享库） |
| 14 | `e1f2a3b4c5d7` | P3.x ticket `ticket_no` 人读业务键（+`seq_ticket_no`） | | | ✓（descends from the P3 head ⇒ 不可落共享库） |
| 15 | `f2a3b4c5d6e7` | P3.3 CMDB 深化 `entity_relation`（关系/拓扑/影响分析） | | | ✓（descends from the P3.x head ⇒ 不可落共享库） |

## 不变式（按集分述）

1. **完备性**：`链 ⊆ B ∪ C` 且 `B ∩ C = ∅`（15 = 11 + 4，**零空洞**）。
2. **可停留性**：`A ⊆ B`，且 A 在链上**连续**（`d4e5f6a7b8c9 → c3d4e5f6a7b8`），为 B 内「当前允许停留」的显式子集。
3. **已分类**：`head ∈ B ∪ C`（本批 head `f2a3b4c5d6e7` ∈ C）。

> ⚠️ 完备性**必须**用 `B ∪ C`。**严禁**用 `A ∪ C`（仅 3/15 覆盖 ⇒ 必误红）。

## 判定式

对 served HEAD 的代码：

> **code-required ≤ live `alembic_version` ≤ 允许停留上界（live ∈ A）**

- `code-required` = `max{ rev ∈ 链 ∩ **B** }`（**上界取 B `MIGRATION_LIVE_APPLICABLE`，自动同步、fail-closed**；采纳需求 seq2373-二／评审 seq2375-二，架构落库 `1286aa8`）。例如 master `6e8c353` ⇒ `code-required = c3d4e5f6a7b8`。
- **为何不用 A 作上界**：A 须**人工**随迁移扩张，漏扩即**静默低配 PASS**（评审合成链实证：在两版间插入 live-applicable `X` 而 A 未扩 ⇒ A-规则 PASS、B-规则正确 BLOCKED）。B 因「新增迁移须同批归类」而自动同步，消除该人漏点。
- **live 合法性**仍用 A：`live ∈ A`（A 是**可停留**值子集）。由 `A ⊆ B` ⇒ `required ∉ A ⇒ ∀ live ∈ A 均早于 required ⇒ 必 BLOCKED`（绝不 PASS）。
- ⚠️ **C 版本不得入上界**：`e8a1b2c3d4f5` 在 `c3d4e5f6a7b8` **之上**，若计入会抬高上界、令正确的 `live=c3d4e5f6a7b8` **误红**；C 只作**完备性分类**（评审 seq2372-二）。**B-based 下该警示依然成立、予以保留**。
- **已分类性**单独校验（∈B∪C）：`∃ 链上版本 ∉ (B∪C) ⇒ NOT RUN`（**绝不低配 PASS**）。
- **判据不是 `live == head`**：live 不应、也不允许迁到 `e8a1b2c3d4f5`。
- 本次真实漂移 = 判定式右半失败：代码需 P2-3（`c3d4e5f6a7b8`），live 停在 P2-MA（`d4e5f6a7b8c9`）。

## 版本合法性 ≠ 功能就绪

- **版本合法**：`live ∈ A`（`LIVE_REV_ALLOWED`）。
- **功能就绪**：代表性触库/鉴权路由**非 5xx**（如 `GET /api/v1/auth/providers`）。
- 二者**必须分开**：`d4e5f6a7b8c9` 是**合法**版本，但 P2-3 代码在其上触库路由 **500**（功能未就绪）——只能由动态闸报出。

## 静态闸 vs 动态闸

- **静态闸（离线锁，单元席）**：迁移图事实 + A/B/C 三集合常量 + `B∪C` 完备性/`A⊆B` 可停留性/head 已分类 + 「版本合法性 ≠ 功能就绪」注。**不连 live、不断言 live 值**。
- **动态闸（live 冒烟，当批 live 执行席，非离线席兼任）**：① `live ∈ A`；② `code-required ≤ live`；③ 代表触库路由 **非 5xx**。不过 ⇒ live 项 **BLOCKED**。
- 门禁纪律：区分 `httpx.HTTPError`(skip) 与 **响应 ≥500(fail/error)**；live 面「未运行」记 **NOT RUN**，不计入通过。

## 流程约束（本席背书，架构 seq2371-三／后端 seq2369-3）

- **任何新增迁移，后端须同批更新本文件并显式归类**（∈B 或 ∈C）；否则该批预核**不绑定**。
- 新增迁移默认为**尚未分类** ⇒ `code-required` 推导遇之即 **NOT RUN**（不低配）。

## 来源

- 后端 seq2338/2344/2346/2351/2369；架构 seq2328/2349/2371（`1286aa8` 落 (a) 上界=B）；需求 seq2326/2337/2339/2352/2370/2373/2375；单元 seq2345/2347/2350；评审 seq2340/2348/2367/2372/2375。
- 迁移文件：`backend/alembic/versions/{c3d4e5f6a7b8_p23_auth_provider,d4e5f6a7b8c9_p2ma_mon_alert_last_event_at,e8a1b2c3d4f5_p2_closeout_mon_alert_dedup,c9e3f1a2b4d6_p3_ticket_kb,e1f2a3b4c5d7_p3x_ticket_no,f2a3b4c5d6e7_p3_3_cmdb_relation}.py`。
