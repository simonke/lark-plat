# P6《受控自动处置（AIOps L4）》需求规格 ＋ 产品设计 v0.1.11

- 状态：**立项基线草案 v0.1.10（对账 r1＋r1.1…r1.11；含 lock-first RED 检查点＋行为 RED/green＋`put_level` 行为回归测试＋审计 list 面 16 键补齐；审计 list green `52991f2`／FE `75a2190`·@代码reviewer 门 PASS·**@集成 live-F round 2 PASS 60/60 ⇒ §30 域级允收通过·本 doc 已终锚·@刘辉「同意」·已 `--no-ff` 合并入 master ＝ `M12=864a3e3`**）**（@刘辉 msg `3503`「6期设计开工」＝立项并起批；msg `3513`「落库 策略化自动批准」＝范围/机制定音）。
- 来源：承 §26《AIOps 演进》四方合稿 v1.0（产品 26.1／架构 26.8／信任 26.5／前端 26.6／KPI 26.2／节奏 26.3）＋ §29.2（E6 顺延）＋ §30（立项基线）＋ @架构 P6 tuple v0.1（msg `3506`）／**tuple r1 冻结（msg `e2066572`·18:21）＋ r1.1（`40076d8e`）＋ r1.2（`2ac308af`）＋ r1.3（`b1e5e5a1`）＋ r1.4（`e0b8e250`）＋ r1.5（`5b1a1257`）＋ r1.6（`664b07bc`）＋ r1.7（`f862d052`）＋ r1.8（`8f72d650`）注记** ＋ 各席设计输入（@集成 `3504`／@前端 `3505`／@单元 `3507`／@后端 `3509`/`3511`）。
- 基线锚：P5.1 终态 **`M11=6740d22a3854798ab2a49725b8d397d37238aa15`**；**★P6 已合并 → 发布锚 `M12=864a3e3ff5be48aa6798d5aba98149da5ec396b7`（`origin/master`·`--no-ff`·parents `[6740d22(M11), 75a2190]`·tree `661533de…` ≡ `75a2190^{tree}` **零漂移**）**。
- **★治理合并锚（追加·v0.1.11）：`M13=6aa402c08cd571bd7eec4b615678e3759f05b7b1`（`origin/master`·`--no-ff`·parents `[864a3e3(M12), fd4070b]`·tree `249ccf32…` ≡ `fd4070b^{tree}` **零漂移**·仅动 2 文件 `backend/tools/live_readiness_smoke.py`＋`backend/tests/test_live_env_allowlist_single_source_lock.py`（+137/−2））。此为 **A2 dwell-override 治理项**（@刘辉 `3707` 裁定 A2／`3730` 授权合并）之合并 tip：**工具/测试面变更·零产品码·零 DDL·零 openapi·paths 仍 173·单头 `P6_REV`** ⇒ **P6 产品发布锚仍 `M12=864a3e3`**；§30.7 台账登记「产品锚 M12 ＋ A2 治理合并 tip M13」两项。治理规格＝`DWELL ⇒ 仅豁免 {C,A} 成员归属否决；链上性＋code-required≤live 恒生效`（点名例外 `f5a6b7c8d9e0`·Tier1 锁常驻／Tier2 gap）。**served `:8000` 仍 M12（app 码 M12≡M13·无需 re-serv）**。
- 代码锚（P6 分支 `p6-aiops`）：**green tip `52991f289825d75f21ae7cc5e3c8220c4f9b1fad`**（父＝审计 list RED `e857723`·链 `7f40298→e857723→52991f2`·**未改写前 tip**）＋配对 FE **`75a21904133e936fc2a6b2f6f07e7913e67c8648`**（单亲 `52991f2`·frontend-only）。**改动**＝仅 `app/services/ai_service.py` **+6/-0**·**零 DDL**·paths 173／单头 `P6_REV` 不变·lock blob `5b7d7a33`／behavior blob `8f998e9a` 未动·`ApprovalRequest(` 构造点 **6**；`_action_out`@`ai_service.py:68` 由 **10→16 键**（A1 直取 4：`approval_mode`/`policy_ref`/`verification_ref`/`rollback_ref`；A2(i) 只读别名 2：`why_ref:=a.basis_refs`／`result:=a.decision`）⇒ `GET /ai/actions` list item **16 键**。**门序**：@单元 审计 list RED `e857723`（2F/11P·collect 664）→ @后端 green `52991f2`（behavior 13/13＋lock 33＝46 passed·全 tests 664/0·ruff clean）→ @架构 `e7180a06` 独立复核 PASS → **@代码reviewer `61736225` 正式门 PASS**（独立探针 13/13·含审计 list 面 16 键∧别名∧auto_policy 行）→ **@集成 live-F round 2 PASS 60/60**@`52991f2`（20:41–23:41·专用库 `lark_plat_p6`·served `:8026`·wt `wt-p6verify` HEAD `match=True`·paths 173·单头 `P6_REV`·**未触共享 `:8000`/共享 `lark_plat`·未跑迁移**；六组断言全 green 含 ★`3644`③ 审计 list 16 键∧别名 `why_ref==basis_refs ∧ result==decision`∧`auto_policy` 真行〔served 发起链真实产出〕；evidence `p6f-livef-0a29a4.evidence.json` sha256 `4AFD3519…5E1BCA`／harness `p6f_aiops_gate.py` sha256 `A0B0CE5E…7F553E`·本席只读复算吻合）⇒ **§30 域级允收通过（绑 clean committed SHA {backend `52991f2`, FE `75a2190`}）**；候 @刘辉 merge order → @架构 `--no-ff` 入 master（预期 M12）。**前一 green tip `7f40298`** 仅覆盖「已交付行为契约面」（44 passed·662/0·构造点 6·flag 关＝P5 字节等同·paths 173），**审计 list 面未闭故不作 §30 终锚**；`v0.1.8`@`7f40298` 随 tip 前移**作废**。 **⇒ 已 `--no-ff` 合并入 master ＝ `M12=864a3e3`（parents `[6740d22(M11),75a2190]`·tree ≡ `75a2190^{tree}` 零漂移）。**
- 口径：本文件为**需求侧基线（WHAT）**，接口/schema/迁移 rev/flag 命名/paths 精确值终值归 **@架构 P6 tuple** 冻结；**E6 核心 r1 已冻结（见 §7），§30.3 候选默认不并入（add-on）**；**冻结前不落码、不改既有冻结口径**。

---

## 0. 立项与范围

**P6 ＝ E6（受控自动处置·L4）核心 ＋ E7/E8（信任底座·加权）**（承 §26.3「自治度越高，E7/E8 权重越大」）。

| 项 | 内容 | 定位 |
|---|---|---|
| **E6** | 受控自动处置（L4）——白名单＋低风险自动执行＋验证指标/熔断/回滚点 | 核心·产品能力 |
| **E7** | AI 治理与信任（升级版）——HITL 分级映射权限码、`ai_action` 全链、证据卡、全局审计视图 | 横切·始终在线 |
| **E8** | 数据/评测基座（升级版）——neg-control 回归集、升级必过门禁、发布前影子执行、反馈飞轮 | 横切 |

**已定音（@刘辉 `3513`）**：
- **落库**：等级/白名单/熔断阈值＝**governed 数据**（**非脚本常量**），**add-only 新表＋新 rev `P6_REV`**（parent `f5a6b7c8d9e0`、入 C 集、单头）；原「零迁移优先」口径**作废**。
- **策略化自动批准**：动作/审计项含 **`approval_mode ∈ {auto_policy, manual}` ＋ `policy_ref`**；**白名单内＋低风险＋等级允许 ⇒ `auto_policy`**（**仍写审计、仍经 `exec+approval` 原语**）；**非白名单／超阈／L3 ⇒ `manual`**。

**智能等级目标**：**自动化等级矩阵 L0..L4**（由后端 governed 下发，FE 不硬编码；L4＝受控自动＝本期内最高启用档）；**不进入 L5 自愈闭环**（§3 非目标）。

**范围待确认（@刘辉 一字）**：§30.3 候选——①「工时」功能（§20.5.1 长悬置）；② backlog #6（`d2` 审计断言收紧）。**默认不并入**本基线；如需并入请明示，需求侧出 add-on 基线后并入。

**非目标（防蔓延）**：不改既有 `exec`/`approval`/`rollback` 语义；不自造执行/CI 引擎；不引入第二数据源；AI **不直接写生产**（除白名单低风险＋可回滚）；不含 L5 自愈闭环；不含 P4/P5 既有能力重做。

---

## 1. 目标与成功判据

- **目标**：对**白名单内低风险**场景，经**预授权（`auto_policy`）**路径自动完成处置（写操作仍落既有 `exec+approval` 记录、**不绕审批**），全程**AI 标识＋证据链＋验证指标＋熔断＋一键回滚**，做到**自治可控、越权=0、可解释可回溯**。
- **产品级 KPI（≠模型级）**：自动处置成功率、**回滚成功率**、**熔断触发即人工介入率**、建议采纳率、MTTR、误报率、**越权=0**、证据覆盖率、建议可回溯率。

---

## 2. 用户与场景（US）

- **US-AI-05**（一线运维/值班）：白名单内低风险告警**自动处置完成**，时间线**醒目「AI 发起」标识**，可**一键回滚**，熔断状态条可见。
- **US-AI-06**（管理员）：配置**自动化等级矩阵（L0..L4）**与**白名单**（等级变更**二次确认＋审计**），审阅 `ai_action`、查看熔断/回滚状态。
- **US-AI-07**（治理/质量）：在**全局 `ai_action` 审计视图**审视全部 AI 动作（含 `approval_mode`/`policy_ref`）；模型/策略/prompt 升级经 **neg-control 门禁**、发布前**影子执行**。

---

## 3. 横切原则与红线（P6 不得破）

1. **三元门**：每能力 ＝ **1 flag ＋ 1 权限码 ＋ 1 审计行**；`ai_action` append-only。
2. **flag 全默认 False**（`ai.auto_remediate` 默认 False）；**路由恒声明·无条件注册（取 (A)，承 P4/P5 先例）**⇒ **committed/served `paths` 恒 `173`**；flag 关＝**运行期门 400/403（非 404）**、不崩；feature-first 门序沿用；**门序＝auth(`401`) → flag(`400/403`) → 路由存在(`≠404`)**；**FE 关态 UI 逐字节不变**。
3. **写操作仍一律经既有 `exec+approval`**（**不绕审批**）；`auto_policy` 仅「审计+`policy_ref`」之别，**禁止新增绕过审批的写入口**；**不复制执行器**。
4. **白名单外一律 L3 HITL（`manual`）**；自动处置**限白名单低风险**且**必绑** 验证指标＋熔断＋回滚点。
5. **输出可解释·可回滚·可复现**：`ai_action` 记 模型名/版本/输入快照/依据/置信度/`trace_id`/decision/`approval_mode`/`policy_ref`/验证结果/回滚点。
6. **检索/处置层数据权限（US-03）**：按 `visible_entity_ids_for(entity_type, actor)` 裁剪；**越权=0**（域级允收**硬项**）。
7. **脱敏＋防注入**：外部/用户文本入 prompt 须脱敏＋边界标注；执行隔离走既有 agent。
8. **契约与迁移**：schema 化＋版本化＋可 diff；迁移 **add-only、单 head、新 rev `P6_REV` 入 C 集**（禁上共享活库）；paths **add-only**。
9. **契约/评测门**：模型/策略/prompt 变更 = 版本化产物，升级**必过评测门禁（含 neg-control）**，发布前**影子执行**。

---

## 4. Epic 需求（含验收方向；终值归 tuple）

### E6 受控自动处置（L4）

- **FR-E6-1 自动化等级矩阵 ＋ 策略（governed·落库）**：`GET|PUT /ai/automation/level`——`GET`（门 **`ai:use`**）→`{current, matrix[]}`（**matrix＝L0..L4 能力/授权，后端 governed 下发、FE 不硬编码**）；`PUT`（门 **`ai:admin`**）幂等（同值 no-op）＋**二次确认＋审计**。等级/策略 `remediation_policy`（`asset_class × op_type → 等级 / 白名单 / 验证指标 / 熔断阈值 / 回滚点`）**落库**。默认 **L3**、上限 **L4**。**`current` 单一·`PUT` 互斥（r1.8 定稿）**：`PUT` 置目标 level `enabled=True`、**其余 level 全部 `enabled=False`**；`GET.current`＝**唯一 enabled 行的 level**（无则默认 `L3`）；同值 **no-op**；**自动门以 `current` 为准（非逐行 enabled）**；schema **不加 `is_current`**（以 `enabled` 互斥表达单一 current）。
  - **验收方向**：默认 L3；**`PUT` 后恰一个 `enabled` ∧ `current==目标` ∧ 两向 PUT 对称（`L4→L2` 与 `L2→L4` 均得 `current==目标`）**；L4 未显式开启 ⇒ 不自动；等级变更产生**二次确认记录＋审计行**；`GET` shape 含 `current`＋`matrix`。
- **FR-E6-2 白名单（governed·落库）**：`GET|POST /ai/automation/whitelist`（集合）＋`PUT|DELETE /ai/automation/whitelist/{item_id}`（条目）——条目 `{action, risk_level, enabled, updated_by, updated_at}`；`risk_level` 与本节风险分级**同源**（**小写唯一字面 `{"low","medium","high"}`**）；列表分页 `page/page_size`＋筛选 `action/enabled`；门 `ai:admin`＋审计。**白名单外 ⇒ 一律 `manual` HITL**（**不自动**）。
  - **验收方向**：白名单外调用**必然**走 HITL（非空洞：构造白名单外动作断言无自动执行）；白名单变更留痕。
- **FR-E6-3 策略化自动批准 ＋ 预授权执行（不绕审批）**：命中白名单＋低风险＋等级允许 ⇒ **`approval_mode='auto_policy'`＋`policy_ref`**：**仍生成 `exec_task`＋`approval` 记录**（审批由策略**预授权**满足），**不新造执行器、不改 `exec/approval/rollback` 语义**；否则 ⇒ **`manual`**（人工 approval）。自动动作写 `ai_action(decision='auto')`。
  - **验收方向**：`auto_policy` 动作**存在** `approval` 记录＋`ai_action(decision='auto', approval_mode='auto_policy', policy_ref=…)`；**静态断言＋行为锁**证明**无绕过 `exec+approval` 原语的写路径**；非白名单／超阈／L3 ⇒ **必回 `manual`**（结构 neg-control）；复用既有执行链（无新 executor）。
- **FR-E6-4 验证指标 ＋ 熔断 ＋ 回滚点**：每个可 L4 的策略**必绑**——① **验证指标**（动作后健康校验）；② **熔断**（阈值突破 ⇒ 立即 halt 后续自动动作＋**升级人工**；`GET /ai/automation/circuit-breaker`→`{state: open|half|closed, threshold, current, last_tripped_at}`）；③ **回滚点**（`POST /ai/automation/runs/{run_id}/rollback`→`{status: rolled_back|not_rollable, reason?, window_expires_at?}`，**幂等**、同终态、不重复补偿、仍走 `exec+approval`）。
  - **验收方向**：**无验证指标的策略不得启用 L4**（fail-closed）；熔断可确定性触发（阈值可注入/env 覆盖）、**超阈降级非 500**；回滚幂等可执行且留痕。
- **FR-E6-5 AI 标识 ＋ 可追溯**：自动动作在事件/审计面**醒目 AI 标识**；`ai_action` 全链（模型版本/输入快照/置信度/依据 `basis_refs`/`trace_id`/decision/`approval_mode`/`policy_ref`/验证结果/回滚点）。
  - **验收方向**：时间线标 **AI 发起**（含 `approval_mode` 徽标）；**建议/动作 ↔ 证据双向检索**。
- **FR-E6-6 门控/隔离/审计**：flag `ai.auto_remediate` 默认 False（关⇒任何调用者 **400/403**、不崩）；权限 **沿用 `ai:use`/`ai:admin`**（r1 冻结⇒perms **16 不变**、paths 仅增 automation 端点）；US-03 按 `visible_entity_ids_for` 裁剪、**越权=0**；`ai_action` append-only。
  - **验收方向**：flag 门序 feature-first(400/403)；**越权=0**（黑盒＋锁 spy 双证，不互替）；审计在场。
- **FR-E6-7 预演（dry-run）＋影子/金丝雀（R3/R4）**：`POST /ai/automation/dry-run`（`ai:use`）→`{idempotency_key, writable:false, items:[{target, params, expected_effect, risk_level}]}`；**只读·零副作用·幂等**——**不落处置 run、不触目标系统**；**落 1 条 `ai_action(decision='dry_run')` 审计行**（可回溯，不违「零副作用」）。L4 上线前**影子执行**（干跑记录）；可选金丝雀（小范围先验）。
  - **验收方向**：dry-run **零处置 run 行**（**不得只断 HTTP 200**）＋可回溯审计行；影子模式**无生产写**且有记录。
- **FR-E6-8 幂等/去重（可注入 seam）**：幂等键＝`action+target+时间窗`；窗口/时钟**可注入**（service 形参 `now`＋常量 `DEDUPE_WINDOW_SECONDS`，可覆写＋env 覆盖）⇒ served 级 live-F 可**确定性**断「同窗去重／越窗重放」。
  - **验收方向**：同窗两次 ⇒ 一次执行；越窗 ⇒ 可重放；边界不 flaky（注入窗/时钟）。

### E7 AI 治理与信任（升级版）

- **FR-E7-1 HITL 分级映射权限码**：建议／需确认／**预授权（auto_policy）** 三级徽标，与权限码绑定（预授权 = L4 前置条件）。
- **FR-E7-2 `ai_action` 全链留痕**：`{model_name, model_version, input_snapshot, confidence, basis_refs, trace_id, actor, decision(adopted/rejected/auto/dry_run), approval_mode, policy_ref, verification_ref, rollback_ref, created_at}`（append-only）。
- **FR-E7-3 证据卡＋置信度＋模型/版本脚注**：**统一组件**（复用 P4 先例），自动动作必带。
- **FR-E7-4 全局 `ai_action` 审计视图**：复用 `GET /ai/actions`（只读，门 `ai:admin`）——分页/筛选 `action`/`target`/`result`；新增 automation `action` 类型值＋**`why_ref`**（rationale ref，可点回源；list 增 `why_ref`/`result`/`approval_mode`/`policy_ref`，承 r1③）。**r1.11（@架构 `966bec92`·19:47·in-scope）**：`_action_out` 增 **A1 列直取** `approval_mode`/`policy_ref`＋**A2(i) 只读投影别名** `why_ref := a.basis_refs`（rationale·可点回源）、`result := a.decision`（处置结果）＋**FR-E7-2 补齐** `verification_ref`/`rollback_ref` ⇒ **list item＝16 键**（现有 10＋6）；**零 DDL·纯 serializer**；**filter 面本轮不动**（`action`/`target` 无承载列）。
- **FR-E7-5 越权=0**：US-03 检索/处置层三面（vector/FTS/hybrid）＋处置面，**黑盒＋锁 spy 双证**。
  - **验收方向**：见各 FR；**越权实体不得进入模型上下文/执行面**。

### E8 数据/评测基座（升级版）

- **FR-E8-1 neg-control 回归评测集**：含**负对照**用例；**升级前后基准不退化**（可判红）。
- **FR-E8-2 升级必过门禁**：模型/策略/prompt 版本变更 ⇒ **必过评测门禁**方可启用。
- **FR-E8-3 发布前影子执行**：新策略/模型**先影子执行**，达标再放行（F**R-E6-7 前置**）。
- **FR-E8-4 反馈标注数据飞轮**：建议卡「有用/无用＋备注」＋错误上报（后端接口）；沉淀可检索判例（承 §26.5 R6）。
  - **验收方向**：neg-control 能变红；升级未过门禁 ⇒ 拒绝启用；反馈可入库、可检索。

---

## 5. 与现有工程衔接（承 P4/P5，不重做）

- **承载面**：E4 `rca_service`（聚合/RCA）＋ E5 `workflow(kind='playbook')`（预案）＋ P3-4 编排引擎；E6 自动处置＝**E5 预案的 L4 放权**，复用既有 `exec+approval/rollback`。
- **既有符号（P4/P5 已立；P6 复用不重声明）**：`ops_event`／`entity_relation`／`ai_action`／flags `ai.enabled`·`ai.rca`·`ai.playbook`／perms `ai:use`·`ai:admin`（16）／`LLMClient`／`visible_entity_ids_for`／`GLOBAL_SCOPE_TOKEN`／`MON_LEVELS`／`WORKFLOW_KINDS`。
- **governed 数据原则**：等级矩阵/白名单/熔断阈值＝**落库 governed 数据**（经 API/seed 读写、env 可覆盖），**非脚本常量**（承 @后端 3511；与 P5.1「常量面」相反，因本次要求可审计/可回滚/可注入）。档位判据仍取**运行时实载常量**（(c) 原则）。
- **现状基线**：alembic 单头 **`f5a6b7c8d9e0`**、paths **167**、perms **16**、seed **27/112**；P6 预期**新增 add-only 迁移（`P6_REV`·单头）＋新增 paths**，精确值归 @架构 tuple。

---

## 6. 建议端点/shape 基线（需求侧采纳各席输入；供 tuple 定名冻结）

**建议端点基线（采纳 @后端 `3518`；path template 计 N、方法不计）**：

| # | path template | 方法 | 门 | shape（要点） |
|---|---|---|---|---|
| 1 | `/api/v1/ai/automation/level` | GET/PUT | `ai:use`/`ai:admin` | `{current, matrix[L0..L4 能力/授权]}`；PUT 幂等＋二次确认＋审计 |
| 2 | `/api/v1/ai/automation/whitelist` | GET/POST | `ai:admin` | 列表 `page/page_size`＋筛选；条目 `{action, risk_level, enabled, updated_by, updated_at}` |
| 3 | `/api/v1/ai/automation/whitelist/{item_id}` | PUT/DELETE | `ai:admin` | 条目更新/删除；`risk_level` 同源 |
| 4 | `/api/v1/ai/automation/dry-run` | POST | `ai:use` | `{idempotency_key, writable:false, items[{target,params,expected_effect,risk_level}]}`；只读零副作用＋`dry_run` 审计行 |
| 5 | `/api/v1/ai/automation/runs/{run_id}/rollback` | POST | `ai:admin` | `{status, reason?, window_expires_at?}`；幂等、走 `exec+approval` |
| 6 | `/api/v1/ai/automation/circuit-breaker` | GET | `ai:use` | `{state, threshold, current, last_tripped_at}`；阈值 governed |

**需求侧计数建议（终值已归 @架构 r1 冻结）**：**N＝6、paths `167→173`（r1③ 冻结）**；审计**复用** `/api/v1/ai/actions`（**不新增 detail 子路径**——list 增 `why_ref`/`result`/`approval_mode`/`policy_ref` 字段即可、`why_ref` 可点回源）。perms **16 不变**（沿用 `ai:use`/`ai:admin`）；**路由恒声明（(A)）⇒ committed/served `paths` 恒 `173`（flag 关亦然）**，flag 关仅**运行期**门 400/403（非 404）。**seed（承 @前端 `3532` 修正）**：**维持 `27/112`、不新增菜单/按钮**——FE 侧栏硬编码＋`hasPerm(code)` 门、新页复用 `ai:admin`；**perms `16` 不变**（r1⑥ 冻结；若 @架构 为 RBAC 树完整性另加**可分配权限点**，则 add-only、非 FE 运行必需、另计）。

**FE 契约补充诉求（供 tuple r1·承 @前端 `d351b798`）**：① `level.matrix` 每级含**能力/授权描述**（供展示）；② `why_ref`/证据**回源跳转目标**明确；③ 自动动作时间线含 **`approval_mode` 徽标**（`auto_policy` 显「策略自动批准·`policy_ref`」）。

---

## 7. tuple r1 冻结对账（@架构 msg `e2066572`·2026-09-26 18:21｜E6 核心）

**★r1 冻结摘要（终值）**：**①** rev＝`P6_REV`／`down_revision='f5a6b7c8d9e0'`（单头·C 集·add-only）；**新表 4**＝`remediation_policy`／`automation_whitelist`／`automation_level`／`circuit_breaker_state`；**不建 `remediation_run`（＝既有 `workflow_run`）**；动作审计**复用 `ai_action`**（add-only 增列 `approval_mode`／`policy_ref`／`verification_ref`／`rollback_ref`）。**②** **复用 `ApprovalRequest`**（增列 `approval_mode` 默认 `'manual'`／`policy_ref`；`auto_policy` 置 `status=approved`）；**E6 禁新增 `ApprovalRequest(` 构造点**（权威白名单 **6**）；**无 `verification_ref` 启 L4 ⇒ 422**。**③** **N＝6**；键名统一 **`{run_id}`**＝`/api/v1/ai/automation/runs/{run_id}/rollback`；审计复用 `/api/v1/ai/actions`、list 增 **`why_ref`**/`result`/`approval_mode`/`policy_ref` ⇒ **paths 173**、`removed==[]`。**④** **flag 单一 `ai.auto_remediate`**（默认 False）；影子＝governed **`mode: shadow|live`**（无子 flag）。**⑤** 阈值单点 `resolve_threshold(provider)`＋env；状态机 **`closed→open→half→closed`** 存 `circuit_breaker_state`；超阈降级**非 500**＋升级人工。**⑥** **paths 173／API perms 16／seed 27/112 均不变**；rev 字符串＝`P6_REV`。**枚举（具名常量·字面唯一·单源·禁内联·r1.3 措辞：均为 P6 净新增符号、基线 0 命中）**：`RISK_LEVELS=("low","medium","high")`@`app/db/models/ai.py`（**P6 净新增并于 `models/ai.py`**；经 `__init__.py` 再导出）、校验门 `risk_level not in RISK_LEVELS ⇒ 拒`；`APPROVAL_MODES=("auto_policy","manual")`@**叶模块 `app/services/ai_automation_constants.py`**（**P6 净新增；不在 `models/ai.py`——避双定义＋models→services 反向依赖**）；**`L4_AUTO_RISK_LEVELS=("low",)`@同叶模块**（r1.6；L4 门＝`risk_level in L4_AUTO_RISK_LEVELS`·禁内联 `"low"`·净新增）；`AI_ACTION_DECISIONS`@`app/db/models/ai.py:24` 加 `"dry_run"`（`AiAction.decision`＝`ai.py:66 String(16)`·**无 `CheckConstraint`/`Enum`**⇒**纯代码零 DDL**）；**L4 门＝仅 `low`⇒`auto_policy`／`medium`⇒需人工确认／`high`⇒禁自动（`manual`）**。**D** served 档符：叶模块 `app/services/ai_automation_constants.py`、`P6_REV="P6_REV"`＋`APPROVAL_MODES`；探针隔离子进程三态、强制 `--pid`、binding 实名匹配、`inconclusive`/absent 分列；served＝符 ∧ 进程绑定。**E** dry-run 同 `idempotency_key` 幂等、不重落审计（恰 1 条 `dry_run`）。**F** live-F 专用受控实例＋env；共享 `:8000` 只读、凭据受限如实登记。**范围**＝E6 核心 r1 冻结；§30.3 默认不并入＝add-on。

**需求侧对账结论**：本 v0.1 与 r1 **逐条一致、无自相矛盾**；**唯一钉正＝审计 list 字段 `why`→`why_ref`（采纳 tuple 权威命名）**（§6／FR-E7-4 已改）。§7 原「待定」六项**全部由 r1 关闭**（下表保留备查）。

**r1.1 注记（@架构 `40076d8e`·2026-09-26 18:22｜闭合 @代码reviewer `2c6300` 2 点／@集成 `6eaabe7d` 回滚断·非改冻结）**：**① `ApprovalRequest.biz_id` 保留 `unique=True`、E6 不改其语义/约束**——不变量＝**「一 `exec_task` 一 `ApprovalRequest`」**（采 @集成 选项 (i)）：**回滚＝新 `exec_task` ⇒ 新 `biz_id` ⇒ 新 approval 行可落、不撞 unique**；回滚审批走**既有 `_approve_linkages`** 派发、**仍经 `exec+approval`**（§6 #5／FR-E6-4）；`auto_policy` 与 `manual` 各对**其自身 `exec_task`**落**恰一条**。若未来确需同 task 多 approval ⇒ 另立 add-only 迁移（**超 E6**）。**② `workflow_run` 冻结「零新列」**：E6 **不**加 `verification_ref`/`rollback_ref`/`rollback_window`；run 级修复上下文（含 `rollback_window`、目标/计划）落 **`workflow_run.context`(JSONB)**（键集在 §30 文档化）；**验证/回滚 ref 权威锚仍在 `ai_action`**（r1① 四列）——单一事实源、杜绝双写。⇒ **r1 表集合／`P6_REV`／N=6 均不变**。

**r1.2 注记（@架构 `2ac308af`·2026-09-26 18:23｜闭合 @后端 `dbaccb2a` 三点消歧＋并 1 锁锚·非改冻结）**：**① `APPROVAL_MODES` 单源＝叶模块 `app/services/ai_automation_constants.py`**（与档位符 `P6_REV` 同模块）；**`app/db/models/ai.py` 不定义、不再导出**（避双定义＋models→services 反向依赖）——**修正 r1「C」**：该枚举**不在 `models/ai.py`**；**`RISK_LEVELS` 原记「仍留」`models/ai.py`**（governed DB 校验源、models 层自洽）——⚠️**该「仍留」措辞已由 r1.3 更正为「P6 净新增并于 `models/ai.py`」（`git grep -i risk @6740d22` 全仓 0 命中），非既存**。**② dry-run「零处置 run」对象钉死＝`workflow_run` 无新增行** ⇒ **`Δworkflow_run==0` ∧ 恰 1 条 `ai_action(decision='dry_run')`**（撤 `remediation_run` 后无他表承载）。**③ 幂等 seam 已钉、无改**＝`now` 形参＋常量 `DEDUPE_WINDOW_SECONDS`（可覆写＋env）——即 FR-E6-8／live-F 确定性依赖。**④ 并入白名单锁锚**：`_KNOWN_BIZ_TYPES=frozenset({"exec","terminal","workflow"})`＝**`approval_service.py:83`**；`_assert_biz_type` **`:86`**(def)/**`:93`**(check⇒未知 **404**) ⇒ **E6 禁新增 `biz_type`、回滚沿用 `exec`**。**另确认** @后端 措辞更正（@集成 `3564` 已收）：**首回滚＝新补偿 `exec_task`⇒新 `biz_id`⇒新落恰 1 approval；重复回滚＝Δapproval/`workflow_run`=0·同终态·不重复补偿**。

**r1.3 注记（@架构 `b1e5e5a1`·2026-09-26 18:25｜收 @代码reviewer `214858` 措辞更正＋迁移利好·非改冻结）**：**① 措辞更正**——`RISK_LEVELS`＝**P6 净新增并于 `models/ai.py`**（**非**「仍留／既存」；`git grep -i risk @6740d22` 全仓 **0 命中**）；`APPROVAL_MODES`＝**净新增于叶模块**（同类既存先例对照＝`TICKET_PRIORITIES`@`app/db/models/ticket.py:37`，那才用「仍留」句式）。⇒ **@单元 lock-first／@集成 neg-control 一律按「净新增符号」断言**（基线 0 命中＝**预期初值红**）、**不得写「既存锚·未改」**。**② 迁移利好**：`AiAction.decision`＝**`app/db/models/ai.py:66 String(16)`·无 `CheckConstraint`/`Enum`** ⇒ `AI_ACTION_DECISIONS` 加 `"dry_run"`（7≤16）＝**纯代码、零 DDL**。⇒ 冻结内容不变。

**r1.6 注记（@架构 `664b07bc`·2026-09-26 18:28｜答 @单元 lock-first 2 问·定稿）**：**① `P6_REV` 取值＝字面 `"P6_REV"`**（迁移 `revision` 与叶模块 `P6_REV` **同值**、**不用 hex**；`g1`「迁移头 == 叶 `P6_REV`」单源绑法正确）。**② L4 自动集＝新增具名常量 `L4_AUTO_RISK_LEVELS=("low",)`**（**单源＝叶模块 `app/services/ai_automation_constants.py`**、与 `APPROVAL_MODES` 同模块）；**L4 门＝`risk_level in L4_AUTO_RISK_LEVELS ⇒ auto_policy`**（`medium`⇒confirm／`high`⇒manual）；**禁内联 `"low"`**；`e4` **钉该符号存在且 `==("low",)`**（不退化到 `RISK_LEVELS`）；**亦 P6 净新增**（基线 0 命中⇒预期初值红）。**③ merge order 归 @架构**（`p6-aiops` 保持本地未 push、禁越权 push）。**④ 位序**＝@后端 green → @前端 → @代码reviewer 门 → @集成 live-F；@单元 RED 全程保绿。⇒ **冻结内容 ＋1 净新增符号（`L4_AUTO_RISK_LEVELS`）、余不变**。（**需求侧倾向已被采纳**。）
**r1.8 注记（@架构 `8f72d650`·18:44｜答 @代码reviewer `3594` 门前提问·定稿）**：**① `put_level` 语义＝单一 `current`·`PUT` 互斥**——目标行 `enabled=True`、**其余全部 `enabled=False`**；`get_level.current`＝**唯一 enabled 行的 level**（无则默认 `L3`）；同值 **no-op**；**schema 不变、不加 `is_current`**（以 `enabled` 互斥表达）。依据 FR-E6-1「`{current(单数), matrix[L0..L4]}`·默认 L3·最高 L4」＋ FR-E6-3「等级**达标**」⇒ `current`＝**当前唯一授权档、非多档并存**。@后端 现实现（只置目标 `True`、`current`＝首个 enabled **升序**）⇒ **`PUT L4` 后 `current` 仍 `L3`（错）**，已改为互斥。**② stale 注释**（`test_p3_5_cicd_lock.py:203`／`test_p4_aiops_lock.py:184`）更至 `test_p6_aiops_lock::test_a2_paths_count_173_and_no_removed`/`==173`。**③ 落地**＝@后端 `5f7e77cb`（＝`214074aa`＋1 提交·**runtime 仅 `put_level`**·paths/6 端点/叶模块符号/门序/auth 未变）。⇒ 本席 §30 **FR-E6-1 已明写**「`current` 单一·`PUT` 互斥（其余 `enabled=False`）·默认 `L3`」（**v0.1.7**）；§30 允收硬项＝`恰一 enabled ∧ current==目标 ∧ 两向 PUT 对称 ∧ default=L3`。**④ 行为证据归属（@单元 `567725b1` 缺口）**：仓内**无 `put_level` 行为测试**（P6 lock 仅断路由在场）⇒ **§30 域级允收「必含」@集成 live-F 断言组**：`default current==L3`；`PUT L4 ⇒ current==L4 ∧ 恰一 enabled`；`PUT L2 ⇒ current==L2 ∧ L4 非 enabled`；同值 PUT no-op；两向对称。仓内 behavior test＝**建议·非阻塞**（回归锁）。
**r1.8-补 注记（@架构 `3602`·18:49｜覆盖缺口裁决）**：全 `tests/` 无 `put_level` PUT→GET 行为断言（`test_p6_aiops_lock.py:117` 仅路由在场）⇒ @架构 **准补**非锁 `backend/tests/test_p6_aiops_behavior.py`（test-only·零 `app/`·**不动 lock blob `5b7d7a33`**）：①初始 `GET⇒current=="L3"`；②`PUT L4⇒current=="L4" ∧ 恰一 enabled ∧ matrix[L4].enabled`；③`PUT L2⇒current=="L2" ∧ L4 非 enabled ∧ 恰一 enabled`（两向对称）；④同值 `PUT L2` no-op。**新 tip test-only·supersedes `5f7e77cb`**（runtime 同·paths/6 端点/叶符号/门序/auth 不变）⇒ **§30 允收锚前移新 tip**、**文档 v0.1.8**（FR-E6-1 正文不变·仅换锚）；**@集成 live-F 仍加同组端到端断言（纵深）**。位序：**@后端 补测报新 tip → @前端 replay → @reviewer 门 → @集成 live-F**。**需求侧附**：断言须确定性（fresh/seed 起·不赖执行顺序；「恰一 enabled」实读状态）。
**P6 green 范围裁决注记（@架构 `3605`·18:51｜live-F 首轮实证）**：@集成 `3603` 实探＋@单元 `3604`＋本席实核 ⇒ **FR-E6-3 `auto_policy` 决策+审计**（全 `app/` 零 `approval_mode='auto_policy'`／`decision='auto'` 写入·`RemediationPolicy` 零消费者）与 **FR-E6-4 回滚补偿/阈值单点/熔断状态机**（`rollback_run` 只翻 status 无补偿·`resolve_threshold` 0 命中）**未落**。§30 FR-E6-2/3/4 明列且验收含**行为** ⇒ **属 E6 green 范围·green 未完成·§30 允收阻塞**（33 锁**全结构性**未暴露）。**行为允收清单**（供 `test_p6_aiops_behavior.py` RED）：E6-3＝`approval_mode='auto_policy' ∧ status='approved' ∧ policy_ref≠None`＋恰 1 `ai_action(decision='auto',approval_mode='auto_policy',policy_ref≠None)`＋**构造点==6**；**负控**（白名单外/`risk=high`/`current≠L4` ⇒ `manual` ∧ 0 `decision='auto'`）；E6-4＝首滚 `Δexec_task==+1 ∧ Δapproval_request==+1 ∧ rollback_ref≠None`、再滚 `Δ0`；**配置 fail-closed**：无 `verification_ref` 启 L4 ⇒ **422**；熔断＝`resolve_threshold` 单点＋env·`closed→open→half→closed`·超阈非 500＋升级人工。**位序重置**：@单元 RED → @后端 绿 → @前端 replay → @reviewer 门 → @集成 live-F（专用库 `lark_plat_p6`）。**@需求 暂缓 v0.1.8 附件·待新 tip 换锚**（FR 正文不变）。
**E6 行为收口定稿（@架构 `49f89e68`·18:52｜准 @需求 `3606` 清单）**：**4 项行为**＝①FR-E6-3 `auto_policy`；②FR-E6-4 **回滚补偿**；③FR-E6-4 **验证指标 fail-closed**（★补① gate 落 **L4 激活 seam**：`PUT /ai/automation/level→L4` 校验 L4 策略集 `verification_ref` 齐备，缺 ⇒ **422**·level 保持原值·fail-closed）；④FR-E6-4 **熔断行为**（★补② `resolve_threshold` 单点＋env·状态机 `closed→open→half→closed`·超阈 halt 后续自动＋升级 `manual`·**非 500**）。33 锁结构面不破。**E6-3 发起 seam 定稿（@架构 `1fad218d`·18:54）**：落**共享核 `exec_service.create_exec_task_record`**（`create_task` 与 workflow engine 同汇此核 ⇒ `POST /exec/tasks` 与 `POST /workflows/{id}/run` 两入口天然齐生效·**构造点仍 ==6**）；3 约束＝① **flag 关＝P5 字节等同**（静默 `is_feature_enabled`·**禁 `require_feature` 抛 400/403**·flag 关 ⇒ row 仍 `pending`·feature-first 400/403 **仅限 AI 端点**）②命中判定（whitelist∧risk∈L4∧current=='L4'∧policy 命中 ⇒ 同 row `auto_policy/approved/policy_ref`＋`ai_action(decision='auto')`＋`_approve_linkages`；否则原样 `pending`）③exec→白名单 `action` 匹配键待 @后端 提案。**§30 允收补**：**flag off ⇒ 共享核行为与 P5 字节等同**。**E6-3 gate 覆盖面补正（@代码reviewer `24ccb847`）**：exec 构造点 **2 处**——共享核 `exec_service.py:176` ＋ **`retry_task` 重试敏感复检 `exec_service.py:454`**（**不经共享核**）⇒ **初判** E6 gate 须同时覆盖 `:176` 与 `:454`（**后经下条 `3616` 定案修订为仅 `:176`·`:454` retry 恒 manual**）；构造点仍 **==6**；`workflow_engine.py:263`（`biz_type='workflow'`）非 exec·勿并入。
**E6-3 定案（@架构 `3616`·18:55·修订 `3611`·收 @reviewer `3615`）**：**①** seam **仅落 `:176`**；**`:454 retry 恒 `manual`**（**不判 E6**·新 row 恒 `pending`·fail-closed·**非绕过**）·**拒加持久列/不改 `exec_task` schema**·构造点==6。**②** 契约＝`create_exec_task_record(..., remediation: dict|None=None)`（默认 `None` ⇒ **P5 字节等同**）；命中⇒同 row `auto_policy/approved/policy_ref`＋`ai_action(decision='auto')`＋`_approve_linkages`。**③** action 键＝`AutomationWhitelist.action==remediation["action"]`（**显式字段**）∧`enabled`；policy=`(asset_class,op_type)`；risk∈L4；level=='L4'。**④** scope **4 项同含 RED**（③④初值预期红）。**⑤** FR-E6-4 补偿源＝原 run `WorkflowRun.context["remediation"]`·窗口=`RemediationPolicy.rollback_window`·经既有 `create_exec_task_record` 建单·`ai_action.rollback_ref` 指补偿 task。**⑥** 审计隔离（负控按 Δ/作用域·非全局 `==0`）。**⑦** `retry` 负向断言。
**E6 列级语义定（@需求·答 @代码reviewer `b23e539e`）**：①`AutomationLevel` 无 `current` 列·`current`＝唯一 enabled 行 level（缺省 L3）；②双 level 源 ⇒ 需求侧倾向策略命中追加 `policy.level=='L4'`（或 `<=current`）·**fail-closed**·归 @架构；③阈值 precedence＝**env > `policy.circuit_threshold` > 内置默认**；④`whitelist_ref` 维持 action-match ⇒ **dead·非权威**（RED 勿依赖）·否则 wire 显式绑定·归 @架构；⑤`AutomationWhitelist.risk_level`＝**权威声明风险**·runtime risk 须 `==` 且 ∈L4·否则 manual；⑥origination **须落 `run.context["remediation"]`**（否则 E6-4 无源）。
**r1.9 补钉定案（@架构 `3618`/`3623`）**：①`current` 派生；②命中须并 **`policy.level=='L4'`**；③阈值 precedence **env > `policy.circuit_threshold` > 默认**；④`whitelist_ref` **非死**（策略→白名单显式引用·命中要求 `policy.whitelist_ref≠None ∧ ==rem["action"]`）；⑤`whitelist.risk_level` **非死**（`whitelist.risk_level∈L4 ∧ rem.risk_level∈L4`·不一致⇒fail-closed）；**A2** 歧义（>1 条同 `(asset_class,op_type)` L4 策略）⇒ **fail-closed `manual`**（弃 id-DESC／不加 DDL）；**B** `PUT level→L4` 校验 **`RemediationPolicy.level` 列**·**空集 或 ∃`level=='L4'∧verification_ref==None` ⇒ 422**（level 保持）；**C** `whitelist.action` 非唯一⇒命中=∃行·RED 固定单行。**本轮零 DDL·保单 head**。**auto 命中全集＝四元∧**。

**r1.10 熔断 served 触发定案（@架构 `a0a5ec5e`／`3635` 收口）**：`GET /ai/automation/circuit-breaker`＝**唯一 served 观测面**·其 `threshold` **须 == `resolve_threshold(db)`**（**非裸 `row.threshold`**）。**阈值链（单点）**＝**env > `policy.circuit_threshold`（`policy` 非空且值非空）> `CircuitBreakerState("global").threshold` > 内置 `DEFAULT`**。**签名（无 `scope` 形参·scope＝服务内常量 `"global"`·单行）**：`resolve_threshold(db, *, policy: RemediationPolicy | None = None) -> int`；`record_verification_result(db, *, policy=None, ok: bool) -> dict`（**确定性·无时钟**：`ok=False`⇒`current+=1`·`>=resolve_threshold(db,policy=policy)`⇒`state='open'`＋`last_tripped_at`；`ok=True`⇒`open→half`／`half→closed`·`current=0`）。**三方口径**：**trip**＝`resolve_threshold(db, policy=<该动作匹配策略>)`（**per-policy 阈值参与开闸**）；**halt（E6 命中）＝只读 `state`**·`open`⇒**强制 `manual`**（升级人工）·**不做阈值比较**（故与 trip 无口径冲突·`state` 全局唯一）；**GET**＝`resolve_threshold(db)`（`policy=None`）⇒ 恒 `env > global 行 > DEFAULT`·**不反映 per-policy（可接受·须文档化：per-policy 仅 trip 生效）**。**live-F 范围**＝**halt＋GET shape/precedence**；**FSM trip/recover（`closed→open→half→closed`）无 served 触发 ⇒ 归 unit `b9`**·本轮不新增端点·**paths 仍 173**。

**r1.11 审计 list 面补齐定案（@架构 `966bec92`·19:47｜in-scope·§30 阻塞）**：`7f40298` 已交付面 PASS，但**审计 list 面缺口＝in-scope（非 add-on）**（tuple r1③／**FR-E7-4** 明列 `GET /ai/actions` list item ⊇ `why_ref`/`result`/`approval_mode`/`policy_ref`·**无 detail 路由⇒list 即唯一审计面**·FR-E7-2「全字段」亦须由 list 承载）。**落法（零 DDL·纯 serializer）**：**A1**＝`_action_out` 增 `approval_mode`/`policy_ref`（列直取）；**A2(i)**＝只读投影别名 **`why_ref := a.basis_refs`**（rationale·点回源）／**`result := a.decision`**（处置结果）；**FR-E7-2 补齐**＝并暴露 `verification_ref`/`rollback_ref` ⇒ **list item＝16 键**（现有 10＋6）；**filter 面本轮不动**（`action`/`target` 无承载列）。**§30 新增允收硬项**：`GET /api/v1/ai/actions` list item **keys ⊇ {`approval_mode`,`policy_ref`,`why_ref`,`result`}** ∧ `auto_policy` 行 `approval_mode=='auto_policy' ∧ policy_ref≠None` ∧ 别名 `why_ref==basis_refs ∧ result==decision`。**位序（自 `7f40298` 续链·禁改写前 tip）**：@单元 补审计 list RED（唯一行为文件）→ @后端 落 `_action_out` → @前端 重 rebase → @代码reviewer 门随 tip 重跑 → @集成 live-F（加③断言）→ 本席 §30.7 重锚（**v0.1.9**；`v0.1.8`@`7f40298` 作废）。

**（以下为收敛前原开项，均已由 r1 关闭）**

1. **`P6_REV` 与表**：新 rev（parent `f5a6b7c8d9e0`、单头入 C 集）＋表列（`remediation_policy`／白名单／等级矩阵／熔断阈值／动作记录；是否需 `remediation_action` 分表 vs 复用 `ai_action`）＋4 归宿同步（`live_readiness_smoke`／`test_live_env_contract_lock`（命名符号、禁内联）／`single_source` expected／docs）。
2. **预授权落库口径**：`auto_policy` 如何落 `approval`（新审批类型 vs 既有 `approval` 扩展）——**须保证不绕审批且不改既有 `approval` 语义**。
3. **端点/shape 定名**（见 §6；需求侧建议 **N=6、paths `167→173`**）＋paths 精确值（`removed==[]`）；审计是否需 detail 子路径。
4. **flag 命名**：`ai.auto_remediate`（默认 False）＋是否需子 flag（如 shadow）。
5. **熔断/验证指标来源**：`/health`／`mon_alert`／`ops_event`；阈值归属 `resolve_threshold(provider)`＋env 覆盖。
6. **计数/契约**：paths 精确值（**恒 173·(A)**）、perms（**16·沿用**）、seed（**维持 `27/112` 不变**——FE 侧栏硬编码＋`hasPerm` 门、新页复用 `ai:admin`；若 @架构 为 RBAC 树完整性另加可分配权限点 ⇒ add-only 另计）、`P6_REV` 字符串。

**需求侧对 @单元 `3525` 7 处 pin 的答复（行为/语义归需求侧；schema/rev/字符串归 tuple）**：
1. **L4 fail-closed（拒码）**：**配置层**「无验证指标的策略启用 L4」⇒ **422**（策略配置校验失败、fail-closed）；**运行期**「默认 L3／L4 未显式开」⇒ **不自动**、转 `manual`（**非错误码**，正常回人工 approval）。
2. **dry-run 幂等**：**同 `idempotency_key` 重复 ⇒ 去重**——返回**同结果**、**不重落 `dry_run` 审计行、不重落处置 run**。
3. **`auto_policy` 落 approval 方式**：需求侧要求**「必有 approval 记录」**（表/`biz_type`/decision 字段形**归 tuple/@后端 pin**）；**不得绕过 `exec+approval` 原语**。
4. **flag 命名**：**单一 `ai.auto_remediate`（默认 False）；不设独立 shadow 子 flag**——「影子执行」＝ **governed 运行模式 `mode: shadow|live`**（L4 live 启用前须 shadow 达标·fail-closed），**非新 flag**（防 flag 膨胀、保 flag-集锁确定）。
5. **`risk_level` 枚举（需求侧钉·与 §30 风险分级同源·**字面唯一＋单一来源**）**：**`risk_level ∈ {"low","medium","high"}`（小写·与既有 `MON_LEVELS`/`WORKFLOW_KINDS`/`AI_ACTION_DECISIONS` 同风格）**；**单一来源具名常量 `RISK_LEVELS = ("low","medium","high")`（禁内联字面；位置 `app/db/models/ai.py`，经 `app/db/models/__init__.py` 再导出·承 @后端 `3549`／先例 `MON_LEVELS`·`WORKFLOW_KINDS`）**——`whitelist` 条目＋`dry-run items[].risk_level` **两处引用同一符号**；**仅 `low` 可 L4 自动**；`medium` 需确认、`high` 禁自动；**L4 自动门＝`risk_level in L4_AUTO_RISK_LEVELS`**（**具名常量 `L4_AUTO_RISK_LEVELS=("low",)`@叶模块 `app/services/ai_automation_constants.py`**·单源·**禁内联 `"low"`**；r1.6 冻结·**P6 净新增**）。**（@后端 `3536` 拟 `LOW|MED|HIGH`；@集成 `3545`／@单元 `3547` 采小写先例 ⇒ 统一为小写唯一字面。）** 表列/`remediation_action` 分表 vs 复用 `ai_action` **归 tuple**（已定＝复用 `ai_action`）。
6. **`P6_REV` 字符串＋4 归宿**：**归 @架构 tuple**（需求侧不裁定 rev 存在性）。
7. **seed 终值**：**维持 `27/112`、不新增菜单/按钮**（@前端 `3532` 修正：FE 侧栏硬编码＋`hasPerm` 门、复用 `ai:admin`）；若 @架构 因 RBAC 树完整性另加**可分配权限点** ⇒ add-only 另计（非 FE 运行必需）。

**需求侧对 @代码reviewer `3528`／`3531`／@集成 `3529`／`3533`／@单元 `3530` 的答复（冻前免返工）**：
- **7. served 档鉴别符（(c)·需求侧要求点名）**：P6 须有**打包内运行期实载具名符号**作「此 served＝P6 档」判据——候选**模块级常量 `P6_REV`（＝迁移标识串）**，探针＝**显式 `getattr(importlib.import_module('app.services.ai_automation_constants'),'P6_REV',None)`**（**叶/纯常量模块**·承 @后端 `3536`／@单元 `3534`／@集成 `3541`；避 lazy-import 假阴性）。**探针形态（采 @代码reviewer `3531`②／@集成 `3533`）**：**隔离子进程**、`sys.path`=P6 worktree、**只 import 目标模块后取符**、不触 app 全量 init（**不建连/不改 flag/不注册路由**）。**三态非空洞**：① 模块缺 ⇒ `ModuleNotFoundError` ⇒ **非 P6 档**；② 模块在·符缺 ⇒ `getattr= None` ⇒ **非 P6 档**；③ 符在且 `==<r1 钉串>` ⇒ **P6**。**served 档合证**＝**档位符 ∧ 进程身绑定**（`pid`/launcher/创建时刻/serve-dir，承 P5.1 `pid 33644` 法）；**`app.__file__` 降为旁证**。**档位符＝代码/迁移版本符（实载常量），≠ governed DB/env 业务配置（level/whitelist/threshold 可覆写）**；**符号名与串归 @架构 r1 点名**（与 §7.1/`3525`B6 的 `P6_REV` 同源）。
- **8. 「不绕原语」具名锚（供 @架构 r1 点名；M11 `6740d22` 实核·@后端 `3536` 勘误）**：`app/services/executors/orchestrator.py::_approval_gate`（`:33`/`:79`，exec 入口闸·**cannot bypass**）／`approval_service.py:97 _approve_exec`（`exec_dispatch.delay` `:110`）·`:115 _approve_linkages`（call `:131`/`:149`）／**`ApprovalRequest(` 既有构造点权威集＝6**（`exec_service.py:176,454`·`schedule_service.py:152,317`·`terminal_service.py:115`·`workflow_engine.py:263`）——**E6 `auto_policy` 零新增构造点、须经既有链**；`AI_ACTION_DECISIONS`（`app/db/models/ai.py:24`·**修正 @单元 `3543` 路径笔误**）**add-only** 加 `"dry_run"`。锁形＝**静态命名符号 grep**（命名符号·禁内联：命中集==权威白名单 ∧ E6 模块 **0 命中**）＋**行为 spy**（断 `auto_policy` 仍落 approval 记录且派发经 `_approval_gate`）。缺具名锚 ⇒ neg-control **空断**。

---

## 8. 位序（五线；对齐 §29.4 先例）

@架构 **P6 tuple v0.1（`3506`）→ @刘辉 范围确认 → 本 §30 v0.1/定稿** → tuple **r1 冻结** → @单元 **lock-first RED** → @后端 → @前端 → **@代码reviewer 门** → **@集成 live-F**（`auto_policy` 仍经原语／幂等去重／熔断／回滚／dry-run／US-03 双证） → 本席 **§30 域级允收**（绑 clean committed SHA） → **@刘辉 merge order** → @架构 **`--no-ff` 入 master** ⇒ **新发布锚（预期 M12）**；团队**禁 force-push**。**tuple 冻结前不落码。** **【执行状态 v0.1.10】**：本链已行至 **§30 域级允收＝通过**（绑 clean committed SHA {backend `52991f2`, FE `75a2190`}·@集成 live-F round 2 PASS 60/60）；**@刘辉「同意」→ @架构 `--no-ff` 已入 master ＝ `M12=864a3e3`（预期 M12 达成·tree ≡ `75a2190^{tree}` 零漂移）。**

---

## 9. 待 @刘辉 确认 / 待办

- **范围一字**：是否并入 §30.3 候选（**工时**功能／**backlog #6**）？默认不并入。
- **@架构 tuple r1 已冻结**（E6 核心，msg `e2066572`·18:21）＋ **r1.1…r1.8 注记**（`biz_id` unique·「一 exec_task 一 approval」·`workflow_run` 零新列·`context` JSONB；`APPROVAL_MODES`/`L4_AUTO_RISK_LEVELS`@叶模块；`P6_REV="P6_REV"` 字面；dry-run `Δworkflow_run==0`；幂等 seam；白名单锁锚 `_KNOWN_BIZ_TYPES`@`approval_service.py:83`；`RISK_LEVELS` 净新增、`decision` 零 DDL；反向依赖护栏 (a)(b)；**r1.8 `current` 单一·PUT 互斥**）：§7 六项定项＋§6 计数终值（N=6/paths 173/perms 16/seed 27/112）＋D served 档符 均已落。**@后端 green**（`5417f75`→`214074aa` test-only→**`5f7e77cb`** 含 `put_level` 互斥）·**@集成 `3589` served 预检 PASS**·**@代码reviewer 锁面 open=0**。**待**：@前端 replay → @代码reviewer 正式门 → @集成 live-F；@刘辉 范围一字。 **【更新·v0.1.10 终锚】**：@前端 replay（FE `31b0019`→rebase `75a2190`）✓·@代码reviewer 正式门 PASS@`52991f2`（`61736225`）✓·@集成 live-F round 2 **PASS 60/60**@`52991f2` ✓ ⇒ **§30 域级允收通过**；**已合并 master ＝ `M12=864a3e3`**（@架构 `77b69c18`·`--no-ff`·push 非 force）。
