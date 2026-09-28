# P4《AIOps 智能化运维》需求规格 ＋ 产品设计 v1.0

- 状态：**立项基线草案 v1.0**（@刘辉 seq3193「开工」＝立项并起批）。
- 来源：承 §26《AIOps 演进》四方合稿 v1.0（产品 26.1／架构 26.8／信任 26.5／前端 26.6／KPI 26.2／节奏 26.3）。
- 基线锚：P3 终态 **`M8=24e80931e4efd04996d87b71a8deb9e1fceb4756`**（`origin/master`）。
- 口径：本文件为**需求侧基线**，接口/schema 终值归 @架构 **P4 tuple v1** 冻结；冻结前不落码、不改既有冻结口径。

---

## 0. 立项与范围

**P4 ＝ E1 ＋ E2 ＋ E3 ＋ E7/E8（最小内核）**（承 @架构 seq3192 建议「甲＋信任底座核心」；E4/E5/E6 留 P5/P6）。

| 项 | 内容 | 定位 |
|---|---|---|
| **E1** | 统一运维事件模型 ＋ 事件工作台 | 基座（数据归一＋单页上下文） |
| **E2** | 智能工单助手 | 承载面＝P3 工单 |
| **E3** | 知识助手 RAG | 承载面＝P3-2 知识库 |
| **E7** | AI 治理与信任（**最小内核**） | 横切·始终在线 |
| **E8** | 数据/评测基座（**最小内核**） | 横切 |

**智能等级**：P4 只到 **L3 人在环辅助决策（HITL）**；**不进入 L4 自动处置**（E6 属 P6）。

**非目标（防蔓延）**：不改既有 `exec`/`approval`/`rollback` 语义；不自造 CI/执行引擎；不引入第二数据源（向量库路线归 @架构 裁决）；AI **不写生产数据**；不含 E4/E5/E6。

---

## 1. 目标与成功判据

- **目标**：把 `monitor/exec_log/audit/ticket/kb` 归一为可检索上下文，于工单/KB/事件三面提供**带依据的辅助建议**，全程留痕、可回滚、可解释、零越权。
- **不变量**：AI 输出**非权威源**；告警/KB 仍为权威；任何写操作经既有执行/审批链。

---

## 2. 用户与场景（US）

- **US-AI-01**（运维工程师）：在一张「事件工作台」上按 实体/时间线 看到五源事件，获得相似处置与依据。
- **US-AI-02**（工单处理人）：在工单详情获得相似工单、建议分类/优先级、建议处置与摘要；一键采纳回填、可否决。
- **US-AI-03**（知识作者/值班）：问答带**依据引用（可点回源）＋置信度**；处置后一键沉淀为 KB 文章。
- **US-AI-04**（管理员）：按能力开关与权限控制、审阅 `ai_action` 全量留痕、可回滚 / 熔断升级人工。

---

## 3. 横切原则与红线（P4 不得破）

1. **三元门**：每能力 ＝ **1 flag ＋ 1 权限码 ＋ 1 审计行**；`ai_action` append-only。
2. **flag 全默认 False**（总闸 `ai.enabled`）；feature-first 门序沿用。
3. **AI 只读生产数据**；写必经 `approval + executor`；**禁止新增绕过审批的写入口**。
4. **输出非权威源·默认建议态**；建议采纳/否决均留痕。
5. **检索层数据权限（US-03）**：RAG 检索与事件时间线**按当前用户可见实体裁剪**（同 `visible_entity_ids`）；**越权实体不得进入模型上下文**（域级允收**硬项**）。
6. **脱敏＋防注入**：外部/用户文本入 prompt 须脱敏＋边界标注。
7. **可解释·可回滚·可复现**：`ai_action` 记 模型名/版本/输入快照/依据/置信度/`trace_id`/decision。
8. **契约与迁移**：schema 化＋版本化＋可 diff；迁移 **add-only、单 head、新 rev 入 C 集**（禁上共享活库）。
9. **观测口径**：模型/策略/prompt 变更 = 版本化产物，升级必过**评测门禁**（含 neg-control）。

---

## 4. Epic 需求（含验收要点）

### E1 统一运维事件模型 ＋ 事件工作台
- **FR-E1-1** 归一五源为统一事件 `{ts, 实体, 动作, 结果, 来源, refs}`，`ops_event` append-only（`source∈{monitor,exec,audit,ticket,kb}`）。**唯一写入缝 `event_service.emit(db,...)`**（五源 service 均经此缝写入）；**forward-only，不回溯/不回填历史**（不改动 P1–P3 既有数据）。
- **FR-E1-2** 查询：`GET /events`、`GET /events/{id}`；`GET /events` 列表**沿用既有信封 `{list,total,page,size}`**（与 P3 一致；如需 cursor 须 tuple 明示例外）。
- **FR-E1-3** 实体上下文时间线：同一 `ref/trace_id` 跨源互跳、单页聚合。
- **验收**：五源经同 `ref/trace` 单页互跳；索引 `(source,ts)`/`(entity_type,entity_id,ts)`/`refs GIN`；**无旁路**＝静态断言（`ops_event` INSERT 仅现于归一层）＋行为锁；forward-only。

### E2 智能工单助手
- **FR-E2-1** `POST /tickets/{id}/ai/suggest`＝建议分类·优先级·处置（默认建议态）；`GET /tickets/{id}/ai/similar`＝相似工单。
- **FR-E2-2** 自动摘要；采纳一键回填表单、否决留痕（写 `ai_action`）。
- **验收**：建议**不得**直接改工单状态（须人工确认）；采纳/否决各产生审计行；建议 ↔ 依据可双向检索。

### E3 知识助手 RAG
- **FR-E3-1** `POST /kb/search/semantic`＝混合检索（FTS＋向量，应用侧余弦）；`POST /kb/ai/answer`＝返回**依据＋置信度**。
- **FR-E3-2** 处置后一键沉淀为 KB 文章（**复用既有 KB 文章创建，草稿态**，人审后发布；不新增写端点）。
- **FR-E3-3** 检索层按 US-03 裁剪（口径见 §7；分派器 `visible_entity_ids_for(entity_type, actor)`）。
- **验收（据 (b) 与 @代码reviewer seq3204 重述）**：每条答案 **≥1 依据**且可点回源；**越权实体不得入上下文（越权=0）**；沉淀产物为草稿、不自动发布；**live-F 断真向量距离＝应用侧余弦**（无 `pgvector`/无扩展）。

### E7 AI 治理与信任（最小内核）
- **FR-E7-1** 命名空间 `ai.*`（`ai.enabled` 总闸；`ai.events`/`ai.ticket_assist`/`ai.kb_assist`）全 default False。**权限码＝共享 `ai:use`＋`ai:admin`**（@架构 tuple v1 `seq3203` 裁定，采纳 FR-E7-1 原案；红线①「每能力 1 权限码」落地为**每条 AI 路由受门控＋per-capability flag**）。**perms 14→16**。
- **FR-E7-2** `ai_action` append-only：`{model_name, model_version, input_snapshot, confidence, basis_refs, trace_id, actor, decision(adopted/rejected/auto), created_at}`。
- **FR-E7-3** HITL 分级徽标（建议／需确认／预授权）；模型网关单点审计出口。
- **验收**：**越权 = 0**；每能力三元门齐；`ai_action` 不可改删。

### E8 数据/评测基座（最小内核）
- **FR-E8-1** 回归评测集（含 **neg-control**）；**评测门须离线可跑**（stub `LLMClient`/`EmbeddingStore`，不依赖网络/真 PG）；断「升级前后基准不退化」＋「neg-control 用例**能判红**」。
- **FR-E8-2** 反馈标注：`POST /ai/feedback`（有用/无用＋备注）；升级必过评测门。
- **验收**：neg-control 必须能判红；反馈落库并关联 `ai_action`/`trace_id`。

### 端点全集（**@架构 tuple v1 `seq3203` 冻结**：新增 8 键）
- E1：`GET /events`、`GET /events/{id}`（2）
- E2：`POST /tickets/{id}/ai/suggest`、`GET /tickets/{id}/ai/similar`（2）
- E3：`POST /kb/search/semantic`、`POST /kb/ai/answer`（2）
- E8：`POST /ai/feedback`（1）
- E7：`GET /ai/actions`（`ai_action` 审计视图，1）
- **E3 沉淀复用既有 KB 文章创建（草稿态），不新增键。**
- ⇒ `paths` **156→164**（`removed==[]` 单调 add-only）。


### 模型网关（横切·接口归 @架构）
- `LLMClient`：`complete()`/`embed()`；本地/云可切；限流/成本/缓存/超时/降级；secrets 走密文**不落仓**；单点审计出口写 `ai_action`。
- **建议**：先 **stub/echo** 实现跑通评测与门禁，再接真实模型（对齐 A/B/C/live 门控）。

---

## 5. 产品设计（信息架构与交互）

- **导航**：新增一级「智能（AI）」，**按权限码 `ai:use` 门控**（采纳 @前端 seq3205 方案 (b)，与 P3 一致、FE 零改 store）；`ai.enabled`/各能力 flag 关时后端 API **400**（feature-first），前端呈现「未启用」空态（不提供绕过入口）。
- **E1 事件工作台** `ops/incidents`：左＝事件流；中＝**上下文时间线**；右＝**AI 副驾**（建议＋依据＋置信度）。
  - 组件：`EventTimeline.vue`／`EntityContextPanel.vue`／`TraceRefLink.vue`。
- **E2 工单助手**：工单详情右侧「建议」卡＋采纳/否决（`v-perm` 控制）。
- **E3 知识助手**：`AnswerCard.vue`（依据引用可点回源＋置信度）；处置后「沉淀为 KB」。
- **E7 治理交互**：统一「证据卡＋置信度＋模型/版本脚注」；HITL 分级徽标；全局 `ai_action` 审计视图。
- **E8 反馈**：建议卡「有用/无用＋备注」。
- **通则**：复用 Element Plus；`vue-tsc` clean；AI 标识/HITL 徽标组件级强制；**不提供绕过审批入口**。

---

## 6. KPI（产品级 ≠ 模型级）

MTTR、降噪率、建议采纳率、自动处置成功率/回滚率、误报率、**证据覆盖率**、**建议可回溯率**、**越权 = 0**、门禁通过率/劣化次数。

---

## 7. 域级允收基线（结构，细则待 @架构 tuple）

每 Epic 逐条核：**flag/权限码/审计** 三元门齐；`paths` 精确值（新键单调 add-only、`removed==[]`）；权限计数；迁移 **add-only 单 head 入 C**；`ai_action` 留痕完整；离线锁 RED→green；live-F 硬项；反假绿（空集合/缺失断言不得判绿；碰撞/负例须真）。

**计数（@架构 tuple v1 补钉#3 `seq3212`）**：`paths` **156→164**；权限 **14→16**；seed `PERMISSION_TREE` **menus 26→27（新增顶级 `ai` 菜单）／buttons 110→112**；角色＝**仅 `admin` 绑 `{ai:use, ai:admin}`**（`operator`/`viewer` 均不绑，承 P3 @需求 seq2662 先例；`test_viewer_role_is_read_only` 不变）；迁移 `P4_REV="e9d8c7b6a5f4"`、C 6→7／链 18。

**US-03 检索层隔离·可判红口径（硬项，承 @代码reviewer seq3197/3204；@架构 tuple v1 `seq3203` C）**：仅断「结果集不含越权实体」会被 **post-filter 假绿**骗过。**冻结为**：
1. `EmbeddingStore.query(query_vector,*,scope,limit)` 把 `scope`（含 `entity_type`）作**查询入参**（接口契约），非返回后过滤；
2. 锁须**对 retrieve-then-filter 判红**：**spy 下探到检索本体**（承 @代码reviewer seq3204①）——`PostgresArrayEmbeddingStore` 断 SQL/`cursor` 参数含 `entity_scope` 谓词；`InMemoryEmbeddingStore` 断**候选集获取方法**（公共 `query` 之下）收到 scope；＋构造「越权实体 embedding 确实存在」负例、断其**从未被取回**（仅断公共入参不够，实现可"收 scope 却忽略"）；
3. **二实现同契约**：in-memory fallback 亦「查询即过滤」、禁 fallback 内 post-hoc；prod/unit 同一可判红语义；
4. **FTS 分支同口径（承 @代码reviewer seq3204②）**：混合检索的 **FTS 候选**亦须断**查询层 scope**（同 spy/负例），或把 FTS 取回**并入同一 `scope` 契约面**（不得游离于 `EmbeddingStore` 之外无裁剪）；
5. **实体→可见域分派器（@架构 tuple v1 C）**：`visible_entity_ids_for(entity_type, actor)`——`host`→`HostRepository.visible_entity_ids`（`repositories/__init__.py:200`）；`ticket`→请求人/处理人/参与组；`kb`→已发布＋所属范围/作者；`audit`→按 `ai:admin`/审计权限；**未定义实体类型 ⇒ fail-closed（拒全部）**。**验收须含 host＋至少一个非 host（ticket/KB）的跨域越权负例**，否则「越权=0」在非 host 面不可判。
6. **live-F 黑盒互证（@集成 seq3206／@架构 seq3207-3）**：低权用户走**真端点**（`POST /kb/search/semantic`、`POST /kb/ai/answer`、`GET /events`、`GET /events/{id}`）；预置唯一哨兵串的**越权 KB chunk**＋唯一 `trace_id` 的**越权 `ops_event`**，断其在检索结果与模型上下文**零命中**（同时覆盖 FTS-only/vector-only/hybrid 三路）；未注册 `entity_type` fail-closed。**live-F 绿不替代锁 spy——二者皆过方收 §27.4 硬项。**

**环境前置**：见 §10.1（ADR#2 已裁 (b) 同库应用层向量，**无 pgvector/无扩展**）。


---

## 8. 五线位序与锚（同 P3）

- **tuple v1＝@架构 `seq3203`（＋勘误#1 `seq3207`：`P4_REV="e9d8c7b6a5f4"`，parent＝`b2c3d4e5f6a8`，C 6→7／链 17→18，add-only 单头入 C、4 归宿同步、不上共享活库）。**
- **位序**：`@架构 P4 tuple v1 冻结 → @单元 lock-first RED → @后端 → @前端 → @需求 域级允收 → @集成 live-F → @代码reviewer 门 → @架构 docs ＋ --no-ff 入 master`（预期新锚 **M9**）。团队禁 force-push。

---

## 9. 术语

L1 自动化／L2 关联降噪／**L3 人在环辅助决策（P4）**／L4 受控自动处置／L5 自愈闭环；HITL＝人在环；RAG＝检索增强生成；neg-control＝阴性对照。

## 10. 依赖与衔接

- **复用**：`entity_relation`（P3-3，拓扑真相源，P4 只扩枚举、**不双建**）；P3 工单/KB＝E2/E3 承载；`approval+executor`＝唯一写路径；`AuditMiddleware` 全局审计。
- **新增（@架构 tuple v1 `seq3203`）**：`ops_event`(append-only)／`kb_embedding(id,doc_ref,chunk_ref,embedding,entity_scope,dim,created_at)`／`ai_action`／`ai_eval_case`/`ai_eval_run`；`LLMClient`(stub=`EchoLLMClient`)／`EmbeddingStore`(`PostgresArrayEmbeddingStore`/`InMemoryEmbeddingStore`；`PgVectorEmbeddingStore`＝P5 可选)／`eval_service.run(cases)->EvalReport`；`visible_entity_ids_for(entity_type,actor)` 分派器；`ai.*` flags、`ai:use`/`ai:admin`；**P5/P6 表不建空壳**。

### 10.1 环境前置（live-F 依赖）
- 隔离 PG（PostgreSQL 16.6 / Windows）**`vector` 不在 `pg_available_extensions`**（仅 `pg_trgm`/`pgcrypto`）⇒ `CREATE EXTENSION vector` 必失败；本机无 Windows 预编译产物、无 Docker/WSL/conda/MSVC。**非仅缺 Python `pgvector` 依赖**。
- **★ADR#2 裁定＝(b) 同库应用层向量（@架构 tuple v1 `seq3203`）**：`VectorEmbeddingStore` 退为 P5 可选；P4 **无 `pgvector` 依赖、无 `CREATE EXTENSION`**；向量存 `kb_embedding.embedding`（数组），**应用侧余弦**；FTS＋向量混合。**★勘误（@架构 seq3286 裁 (b)）：「embedding 与 KB 文档同事务写」＝P5 属性、P4 未交付**；P4 仅冻 `EmbeddingStore.upsert` **接口契约**（`app/` 内**零调用者**），article→vector **摄取缝顺延 P5**（P5 台账：`create_article`/`update_article` 发布态→分块→`LLMClient.embed`→`build_embedding_store(db).upsert` 同事务、`doc_ref=str(article.id)`、update 幂等替换、存量回填、成本/限流、public/global token）。⇒ **live-F 不再需要 `vector` 扩展**，环境层假绿消除。
- **需求侧登记**：E3 硬项「答案带依据＋置信度」与「live-F 断真**向量距离（应用侧余弦）**」**以 (b) 实现口径为准**；`live_readiness_smoke.py` 不再断言扩展（(b) 无扩展前置）。
