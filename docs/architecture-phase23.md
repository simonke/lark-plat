# lark-plat 自动化运维平台 — 二期/三期架构设计 v3.0

版本: v3.1（草案，对齐需求 v1.2；2026-09-24 P3 立项补全：新增 CMDB 深化、编排/CI-CD 拆批 P3-3/4/5）  |  日期: 2026-09-08／2026-09-24  |  作者: 架构师

> 承接 v2.1 终态（权威根 4309005）。本文档为二/三期新增能力的架构设计，全部模块对一期 MVP 采用 **add-only 扩展**：不修改既有 434 基线行为、alembic 保持单 head、新能力经 feature flag 可切。接口契约增量见 `api-design-v3.md`。

## 1. 范围界定

| 期 | 模块 | 对应需求 | 状态 |
|----|------|----------|------|
| 二期 | 文件分发 | FR-14/15（上传分发/回传） | 本设计 |
| 二期 | 监控告警 | FR-25/26（指标采集/告警规则/通知联动）+ 外部监控生态对接（Prometheus/ELK/SkyWalking，刘辉 D2 定方向 2026-09-08） | 本设计 |
| 二期 | 身份集成 | LDAP / OAuth2 SSO（对齐一期登录页预留形态） | 本设计 |
| 二期 | 执行器扩展 | SSH 直连降级（架构决策 2 预留位启用）+ Windows 执行器 | 本设计 |
| 三期 | 工单 | FR-27（运维工单流程） | 已交付（P3-1） |
| 三期 | 知识库 | 知识沉淀（关联脚本/资产/工单） | 已交付（P3-2） |
| 三期 | CI/CD 集成 | 发布编排段（消费流水线产物→触发/记录发布→灰度/回滚→审计；不自造 CI 引擎，对接 GitLab CI/Jenkins） | 本设计（P3-5） |
| 三期 | CMDB 深化 | 资产关系/拓扑/影响分析（**深化非新建**；一期 `asset`/`asset_host` 为浅台账） | 本设计（P3-3） |
| 三期 | 编排 Playbook | 步骤依赖 DAG（wait_for/on_success/on_failure）+ `workflow` 服务 / `workflow_run` 状态机 | 本设计（P3-4） |

## 2. 总体架构演进（增量）

```
一期已有                                     二期/三期增量
┌──────────────────────────────┐   ┌─────────────────────────────────────┐
│ 应用层 FastAPI 模块化单体      │ → │ + source/ (文件位置管理)              │
│   auth asset exec script     │   │ + transfer/ (分发引擎)               │
│   schedule approval notify   │   │ + monitor/ (采集/规则/告警)           │
│   audit ws agent terminal    │   │ + sso/ (LDAP/OAuth 认证适配)        │
│   dashboard                   │   │ + ticket/ (工单) + kb/ (知识库)      │
│ + Celery 执行分发/定时/通知    │ → │ + Celery monitor_ingest/alert_eval   │
├──────────────────────────────┤   ├─────────────────────────────────────┤
│ 数据层 PostgreSQL/Redis       │ → │ + metric 时序表(按日分区)           │
│                              │   │ + file_package/file_node/dist_*    │
│                              │   │ + monitor_rule/alert_*；ticket/kb  │
└──────────────────────────────┘   └─────────────────────────────────────┘
▸ 被管主机 Agent（Go，WS 长连） → Agent 协议扩展：file_send/file_recv/
                                     metric_metric（batch）；Windows 构建
▸ SSH 直连（一期预留抽象）       → SshExecutor 启用（connector=ssh 主机）
```

架构决策（增量，继承一期 6 决策）：
1. **传输通道抽象**：`TransferChannel` 接口 → `AgentChannel`（WS 帧）/`SshChannel`（SCP/sftp 降级）。文件分发优先 Agent 通道，SSH 通道为降级与无 Agent 主机兜底。
2. **指标入轨**：Agent 心跳已上报 `metrics{cpu,mem,disk}`（一期 §12 帧协议）→ 二期落库时序表；新增 `metric` 帧支持批量补推与扩展指标。
3. **告警与通知解耦**：告警引擎只产出 `mon_alert_event_log`，投递复用 `notify` 模块多渠道（飞书/邮件/企微/钉钉/webhook），不新建第三方渠道。
4. **认证适配器**：`AuthProvider` 抽象（local/LDAP/OAuth2），本地认证与外部认证统一签发既有 JWT，权限模型完全复用一期 RBAC 与数据权限。
5. **SSH 降级安全等价**：SSH 通路沿用凭据 AES-GCM 解密、命令审计全留痕、敏感规则对 SSH 同样生效（防降级绕过审批）。
6. **工单-执行联动**：工单可关联审批单/执行任务作为处理证据；敏感操作仍走一期不可绕过审批，工单不提供绕过通道。

## 3. 文件分发（FR-14/15）

### 3.1 能力
- 上传文件/目录 → 创建分发任务 → 指定目标主机（单机/批量/按分组）→ 经 Agent 通道推送至目标路径 → 逐主机 sha256 校验 → 结果回传。
- 回传（拉取）：从目标主机指定路径拉取文件回平台存储（限目录白名单）。
- 分发历史/重试/断点续传（Agent 通道按 chunk 游标续传）；大文件分块 + 校验；分发限速可配。
- 敏感主机/大集合同走一期审批联动（可选，默认关闭，避免误伤——设计开放配置 `transfer.approve_on_sensitive`）。

### 3.2 数据模型（新增表，全部 add-only）
- `file_package`：上传文件包（platform 存储，sha256, size, store_path, owner_id, created_at）。
- `file_item`：包内文件（相对路径, size, sha256, chunk_size）。
- `transfer_task`：分发/拉取任务（mode=push|pull, package_id 或 source_host_path, target_path, host_ids, status, created_by, created_at, finished_at）。
- `transfer_host`：任务×主机（status: pending|pulling|transferring|verifying|success|failed|retry, current_offset, verify_sha256, error, started_at/finished_at）。
- `transfer_log`：逐主机传输日志（seq, level, content, created_at）——复用 exec_log 分区思路（按 transfer_task_id 分区前缀）。

### 3.3 时序（push）
```
前端 → POST /transfer/tasks {mode:push, package_id, target_path, host_ids}
后端 → 创建 transfer_task(awaiting/ready) → Celery transfer_dispatch
transfer_dispatch → 逐主机：经 AgentChannel send 帧 file_send{host, file_item, offset:0}
Agent 收到 → 落盘 temp + 累进写 offset 回传 → 完成 → file_verify{sha256}
后端 perHost 校验 → transfer_host.status=success/failed → 通知（复用 notify）
前端 GET /transfer/tasks/{id} + /hosts/{thid}/logs 实时进度（可 WS /ws/transfer 复刻 exec 模式）
```

## 4. 监控告警（FR-25/26）— P2-MA 设计面（2026-09-08 锁定）

### 4.1 能力
- **归一化事件模型（一级设计面，全链路唯一消费形态）**：
  ```
  MonEvent{ source, kind[metric|alert|log|apm],
            entity(host/app), ts, value/severity, labels, raw }
  ```
  - `kind` 统一四类：metric（指标采样）/ alert（告警）/ log（日志条目）/ apm（链路与应用指标）；
  - 审计/规则评估/收敛/升级/notify 全链路**只消费归一化 MonEvent**；`source` 不排他、规则不区分来源；
  - `raw` 保留原始报文供取证与问题定位。
- **adapter 接入双轨（来源并存、不互斥）**：
  - ① 自采集：Go Agent 轻量采集扩展（CPU/内存/磁盘/网络/进程），新 `metric` type 帧向后兼容，直接产归一化 MonEvent 入站；
  - ② 外部 adapter：`monitor_adapter`（prometheus|alertmanager|elk|skywalking|webhook），配置化接入、独立启停——
    - **Prometheus 双通道**：指标远端写（remote_write 拉取归一化）+ Pull 拉取，均鉴权可选；
    - **Alertmanager webhook** 推送告警（兼容其 alert JSON 结构）→ 归一化 `kind=alert`；
    - **ELK**：日志检索键接入平台检索面（复用审计/日志统一入口，安全与权限红线不回落）→ `kind=log`；
    - **SkyWalking**：APM 指标/链路告警归一化进入评估 → `kind=apm`；
    - **webhook 通用型**：任意第三方 JSON → 平台标准告警事件（字段映射可配）。
- 指标采集：Agent 心跳 metrics 落库 + 指标帧批量补推；保留策略 raw 7 天 + 日聚合（`mon_metric_daily`）。
- 告警规则：metric_name + condition_operator + condition_threshold + condition_duration_seconds(持续时长) + 生效范围(scope_type/scope_ids) + cooldown_seconds(静默窗口) + level——字段命名以 api-design-v3.md §2 / `MonRuleCreate` 为准；规则作用于归一化事件，不区分自采/外部来源。
- 告警引擎（Celery beat）：周期扫描最近窗口指标/事件 → 评估触发 → **alert 生命周期 pending→firing→resolved** + **收敛（dedup/聚合同源重复）+ 升级（escalation 逐级提级）** → 复用 notify（场景 scene=alert_fire/alert_resolve）。
- 告警处置：列表/详情/确认(acknowledge)/恢复(resolve)/手动触发规则测试；告警历史可查。
- 实时推送：WS `/ws/monitor` 订阅指标/告警（帧协议权威见 api-design-v3.md §2；subscribe 范围服务端按 US-03 强制过滤）。

> **实现口径（裁定 R seq1804，终版冻结）**：sweep 入口 `monitor_service.sweep_active_alerts`（Celery 任务 `app.tasks.monitor_tasks.monitor_alert_sweep`，beat 固定 30s tick，运行时读 `config_rule monitor.sweep_interval`，未到则跳过）；活跃集 `MonAlertRepository.active()`；metric 新鲜度锚 `mon_alert.last_event_at` + `config_rule monitor.metric_freshness_seconds`（默认 300，stale 不 firing/不升级）。可见性唯一源 `HostRepository.visible_entity_ids`（ip∪hostname∪id）；WS 唯一裁剪 seam `monitor_ws.clamp_subscription`（与 REST 同源）。非 admin 对 app/service 型实体 fail-closed（功能限制，登记 P3 ⑨，本批不扩面）。

### 4.2 数据模型（表名遵循一期前缀惯例：`mon_*`；API 路由仍为 `/monitor/*`）
- `mon_metric_sample`：host_id, metric_name, value, ts（按日分区 + (host_id, metric_name, ts) 索引；raw 7d 后清理，聚合入 `mon_metric_daily`）。
- `mon_adapter`：name(unique), type(prometheus|alertmanager|elk|skywalking), endpoint, config(JSONB，密钥类密文), enabled, status(healthy 等), error_message, last_heartbeat, metrics_received_count, created_by。（对齐落地 schema `{name,type,endpoint,config,enabled}`，旧 `direction`/`kind` 字段已弃用）
- `mon_event_inbox`：归一化 MonEvent 入站（source, kind, entity, ts, value, severity, labels(JSONB), raw(JSONB), received_at）——规则评估前暂存/去重（按 source+event_id 幂等——外部 webhook/remote_write 可携带 event_id）。
- `mon_rule`：name, description, enabled, event_source(null=all), event_kind(metric|alert|log|apm), metric_name(event_kind=metric 时必填), condition_operator(>,<,>=,<=,==,!=), condition_threshold, condition_duration_seconds(持续达阈值秒数), scope_type(host|app|service|null=all), scope_ids(JSONB {ids:[entity_id]}, 生效范围), level, cooldown_seconds(静默窗口), converge_sec(收敛窗口), escalation_enabled, escalation_after_seconds, escalation_severity, escalate_levels(JSONB，逐级升级), notify_scene, notify_channel_ids(JSONB, 复用 notify), created_by。（对齐落地 schema，旧 `kind/op/value/duration_sec/silence_sec` 字段已弃用）
- `mon_alert`：rule_id, entity(source: kind, host/app), source(agent|prometheus|alertmanager|elk|skywalking|webhook), **status(pending|firing|acknowledged|resolved)**（suppressed 为收敛窗口内 transient 标记，不持久化独立态）, fired_at, resolved_at, last_value, extra(JSONB)。
- `mon_alert_event_log`：alert_id, action(fire|acknowledge|escalate|resolve|suppress), from_status, to_status, severity, detail(JSONB), operator_id(→sys_user), at, remark——append-only 留痕。

### 4.3 告警状态机（mon_alert.status）
4 主态 + suppressed（transient 收敛标记，不持久化）：

| 当前态 | 条件命中 | 持续命中达 duration | 条件恢复 | 收敛窗口内重复 | 人工 ACK | 人工 Resolve | 升级 |
|--------|----------|--------------------|----------|----------------|----------|--------------|------|
| pending | pending | **firing** | resolved | suppressed | — | resolved | — |
| firing | firing | firing | **resolved** | suppressed | **acknowledged** | resolved | firing(sev↑) |
| acknowledged | acknowledged | acknowledged | **resolved** | suppressed | — | resolved | acknowledged(sev↑) |
| resolved | pending | pending | resolved | suppressed | — | resolved | — |
| suppressed | pending | pending | resolved | suppressed | — | resolved | — |

转移事件枚举：`fire|acknowledge|escalate|resolve|suppress`；留痕表 `mon_alert_event_log(action, from_status, to_status, severity, detail, operator_id→sys_user, at)`。

- 收敛（dedup，裁定 O1/R2 终版）：活跃期同 `(rule, entity)` 由 `active_by_rule_entity` 复用同一行；resolve 后 `converge_sec` 窗口内再次命中由 `_try_converge`（`MonAlertRepository.recently_resolved`）**reopen**（resolved→pending），置 `pending_since` re-arm 并写 `last_event_at`；`converge_sec=0` 正常新建。通知静默由 `cooldown_seconds` 独立承担（记 action=suppress）。升级由 `escalate_levels` 逐级提级，写 action=escalate。
- 并发/竞态：state_store 用 CAS 乐观锁（rule_id+entity+收敛键唯一）；超时未收到事件 → 自动 resolved（可配，默认 10min）；已触发告警保留原规则快照；from_status→to_status 非法转移拒绝（TRANSITIONS 白名单）。

## 5. 身份集成（LDAP / OAuth2 SSO）

### 5.1 能力
- 登录页多方式（一期已预留）：账号密码 / LDAP / OAuth2（如内部 IdP，可扩展）。
- LDAP：bind 认证（`provider bind_dn 模板 + search`），返回用户身份 → 本地用户按 `map_key(username|email|uid)` 匹配，可自动建档（`auto_provision` + 默认角色）或仅绑定既有用户。
- OAuth2：授权码模式（state 防 CSRF，redirect_uri 白名单），换取 profile → 同样映射/建档。
- 外部认证成功后统一发一期 JWT；本地密码用户与外部用户并存（`auth_source` 区分，互不干扰）；登出/刷新/权限/数据权限全复用。

### 5.2 数据模型（对 users 做 add-only 扩展）
- 新增独立表 `auth_provider`（type=ldap|oauth2, name, config_enc(JSON 串，密钥值逐值 `"enc:"` 密文), enabled）。
- `users` 新增可空列：`auth_source`（default 'local'）、`external_id`、`last_external_login_at`——mvp 已冻结，采用 **additive migration**（nullable 列 + default）。
- `config_rule` 扩展命名空间 `sso.auto_provision`, `sso.default_role_codes`（JSONB 配置，不新增表）。
- `auth_provider.config` 可选键 **`roles_claim`**（add-only，P2-ID §3-v2.1 裁定 seq2090/2092）：声明 IdP 角色断言字段名，外部登录据此取角色；不自动授予 admin/超管（O1）。读取密钥类键不回显明文，`config_mask` 逐值掩码（`ab******yz`/`****`）。

### 5.3 认证流程（OAuth2 示例）
```
GET /auth/oauth/{provider}/login → 302 IdP（带 state）+ 本地落 state(Redis, 5min)
IdP 回调 GET /auth/oauth/{provider}/callback?code&state → 校验 state
后端 POST IdP token 端点(grant_type=authorization_code, client_secret 解密) → 取 profile
映射/建档 → 签发 {access_token,refresh_token,user{...}}（同本地语义）
前端 /auth/me 返回一致；登录页形态切换由 provider 列表驱动
```

## 6. 执行器扩展（SSH 直连降级 + Windows）

### 6.1 SSH 直连降级
- `host.connector=ssh`（一期字段已有）时启用 `SshExecutor`：paramiko 连接池（复用 source_credential），密钥/口令按一期凭据加解密；执行/回显/终止/超时语义与 Agent 执行器对齐；日志经同一 exec_log/WS 通道。
- 降级触发：Agent 断线且主机配置允许 SSH 降级（`config_rule executor.ssh_fallback=true`）→ 任务路由自动切 SshExecutor；审批/敏感判定在降级路径同样生效。
- 安全：SSH 通道写审计、凭据不落日志、连接指纹校验（`known_hosts` 白名单或首次信任+锁定）。

### 6.2 Windows 执行器
- Go Agent 增加 windows 构建：`agent.exe` 原生运行；执行使用 `powershell`/`cmd`（按 script.type）；目录/路径 Windows 化；进程树终止（job object）；无 pty 交互（Web 终端 Windows 会话仅回显流，不做 tty resize 语义，标注降级）。
- 增补帧语义：`exec begin` 携带 os 差异信息；`exec_log level` 沿用。
- 测试：Windows CI 或受控测试机冒烟；AGENT 版本/OS 枚举展示于主机详情（一期 `os_type` 扩展 win）。

## 7. 工单（FR-27，三期）

### 7.1 能力
- 工单生命周期：`create → assign → accept → processing → done → close`（支持 reopen + cancel）；分类（故障/变更/请求/其他）；SLA 目标(可选)。
- 工单内关联：目标主机/资产、关联执行任务（作为证据）、关联审批单；评论留痕；附件。
- 敏感操作从工单发起时仍走一期不可绕过审批（工单不提供绕过通道）。

### 7.2 数据模型
- `ticket`：ticket_no(人读业务键，`TK-YYYYMMDD-NNN`，全局唯一、不可变、服务端生成), title, category, priority, status, requester_id, assignee_id, team_id(可选), description, sla_due_at, resolved_at/closed_at, created_at。
- `ticket_comment`：ticket_id, author_id, content, at——append-only。
- `ticket_attachment`：ticket_id, file_id(复用 file_package 存储), at。
- `ticket_ref`：ticket_id, ref_type(exec_task|approval|asset_host|schedule|kb_article|script), ref_id。

## 8. 知识库（三期）

### 8.1 能力
- 文章 CRUD + 分类/标签 + 版本历史（复刻 script 版本语义）+ 可见级（public/internal/classified，内附和 switch 到 RBAC 角色/主机组）。
- 全文检索（Postgres FTS，中文分词扩展后续可选）；关联引用（文章↔脚本/资产/工单）。
- 净化：指令类内容高亮与一键转执行（引用脚本时校验权限）。〔**deferred**：P3-2 未实现，留后续批〕

### 8.2 数据模型
- `kb_article`：title, category_id, visibility, current_version, author_id, summary(摘要), created_at/updated_at。
- `kb_article_version`：article_id, version, content(Text，append-only，正文单一真相源), editor_id, at。
- `kb_category` / `kb_article_tag`（tag 复用一期 tag 枚举思路）；分类树**深度≤3**（超限 422）、**禁回环/自环**。

## 9. CI/CD 集成 + 编排（三期 P3-4/P3-5，先立架构）

- **Pipeline 抽象**：`pipeline → stage[] → step[]`；step 可触发 exec_task（复用执行链路）、自定义回调、等待人工审批（复用审批链路）。
- **编排**：步骤间依赖 DAG（wait_for/on_success/on_failure），在 Celery 之上实现工作流调度器（`workflow` 服务 + `workflow_run` 状态机），不做新框架（避免过度设计）。
- 与工单/知识库/告警联动（发布变更工单引出流水线等）作为三期后续细化内容，本版只立概念与边界。

> **立项拆分（2026-09-24 刘辉裁定）**：本节两能力拆为独立批次——**编排＝P3-4**（`workflow`/`workflow_run`，复用 exec_task/审批原语）、**CI/CD 集成＝P3-5**（收敛为「发布编排段」，对接 GitLab CI/Jenkins、不自造 CI 引擎）。本节保留概念与边界，细化分属两批。

## 10. 非功能与兼容红线

- **不破坏 234 基线**：全部新功能独立模块/新表/新路由；既有行为零改动；新增测试合计在新文件（锁定稿模式）。
- **alembic 单 head**：二期/三期迁移按批次单链推进；`users` 仅在必要时加 nullable 列。
- **feature flag**：`config_rule` 命名空间 `feature.transfer/monitor/sso/terminal_ssh/ticket/kb` 控制开关（`feature.ticket`/`feature.kb` 门控**行为**、不门控路由，默认 False），默认按批次上线。
- **分区继承**：metric/transfer_log 沿用 exec_log 按月分区模式（添加迁移+保留策略）。
- **时序安全**：新增接口全部走一期 `Result` 信封/分页/权限依赖/审计中间件，无旁路。

## 11. 批次与里程碑（建议）

| 批次 | 内容 | 依赖 | 门禁出口 |
|------|------|------|----------|
| P2-1 | 文件分发（传输通道+任务+前端） | 一期 Agent 帧扩展 | 234+新增全绿 |
| P2-2 | 监控告警（采集落库+规则+引擎+通知联动） | P2-1 前 Agent 帧 | 同上 |
| P2-3 | LDAP/OAuth SSO | 一期 auth | 同上 |
| P2-4 | SSH 直连降级 + Windows 执行器 | P2-1 通道抽象 | 同上 |
| P3-1 | 工单 | 一期审批/执行 | 同上 |
| P3-2 | 知识库 | 一期脚本库 | 同上 |
| P3-3 | CMDB 深化（资产关系/拓扑/影响分析，数据底座） | 一期 asset/asset_host | 同上 |
| P3-4 | 编排 Playbook（`workflow` + `workflow_run` DAG 调度） | 一期 exec_task/审批 | 同上 |
| P3-5 | CI/CD 集成（发布编排段，对接 GitLab CI/Jenkins） | P3-4 | 同上 |

每批走既有流程：需求细化 → 本席设计定稿 → 开发 → 评审 → 单测 → 集成 live → 需求允收。

## 12. CMDB 深化（三期 P3-3：资产关系 / 拓扑 / 影响分析）

> 定位：**深化非新建**。一期 `asset_host`/`asset_group` 为「浅台账」（仅主机与分组），本批在其上加 **CI 关系**、**拓扑邻域**、**影响分析** 三层；不改一期列语义、不引入图库；新能力 flag 默认关。

### 12.1 能力
- **关系管理**：CI 间**有向关系** `src→dst` + 类型词表；CRUD、**幂等**（同 `(src,dst,rel_type)` 唯一，重复创建返回既有行）、**禁自环/重边**；US-03 数据权限一致、写操作记审计。
- **拓扑**：给定 CI 展开**邻域**（上/下游）⇒ 节点 + 边；**深度**默认 2、**硬上限 3**（超限返回 **422**，对齐 KB 深度惯例；`config_rule cmdb.topo_max_depth` 仅可**下调**）；**环安全**（visited 集合，遇环不展开亦不报错）。
- **影响分析**：给定 CI 求**下游可达集**（故障影响面，可选上游）⇒ 受影响 CI 集 + 计数；同为**环安全**遍历、**深度默认 2 / 硬上限 3**（超限 422）。
- **手工维护**：不做自动发现。**非目标**：不改 `asset` 列语义、不做图库/大屏、不做自动发现/探活。

### 12.2 数据模型（新增表，add-only；与 §26 AIOps 拓扑**同表复用**）
- **`entity_relation`**（★ **P3-3 定义、为唯一关系真相源**；§26 AIOps 拓扑**复用本表，不双建** ⇒ **「同表复用」= YES**：采纳 §26 提案之原名 `entity_relation`，**不另建 `cmdb_ci_relation`**）：
  - `id` BIGINT PK；
  - `src_type` VARCHAR(32)（CI 类型；初值枚举 `host` | `host_group`，**可扩展**）；`src_id` BIGINT；
  - `dst_type` VARCHAR(32)；`dst_id` BIGINT；
  - `rel_type` VARCHAR(32)（词表初值：`depends_on` | `runs_on` | `connects_to` | `member_of` | `hosts`）；
  - `properties` JSONB NULL（weight/port 等可选，未来用）；`remark` VARCHAR(256)；
  - `created_by` BIGINT NULL；`created_at`/`updated_at`（TimestampMixin）。
  - 约束：**UNIQUE(`src_type`,`src_id`,`dst_type`,`dst_id`,`rel_type`)**（重边去重）；**CHECK 禁自环**（`NOT(src_type=dst_type AND src_id=dst_id)`）。
  - 索引：`(src_type,src_id)`、`(dst_type,dst_id)`、`(rel_type)`。
- **CI 抽象**：CI ＝ **(type,id) 二元组**，**不引入独立 CI 表**；`*_type` 初值 `host|host_group`（复用 `asset_host`/`asset_group`），端点校验 `type`∈枚举且 `id` 存在；未来扩节点类型仅扩枚举/词表。
- **无独立拓扑/影响表**：拓扑/影响为**查询期计算**（递归 CTE），不物化，避免双真相源。

### 12.3 接口（REST；全部走一期 `Result` 信封 / 分页 / 权限依赖 / 审计）
- `GET  /assets/relations`（`asset:relation:list`）：分页；筛选 `src_type/src_id/dst_type/dst_id/rel_type`。
- `POST /assets/relations`（`asset:relation:add`）：**幂等**创建（重复 → 返回既有行，不 409）。
- `DELETE /assets/relations/{id}`（`asset:relation:del`）：**首删 200（`Result` 信封）／目标缺失 404**（沿用平台 DELETE 惯例；POST 侧幂等返既有行）。
- `GET  /assets/cmdb/topology`（`asset:topo:view`）：`entity_type,entity_id,direction∈{up,down,both},depth(默认 2 / 硬上限 3，超限 **422**),rel_types[]` ⇒ `{nodes[{type,id,label,role∈{root,up,down}}],edges[{src:{type,id},dst:{type,id},rel_type}],truncated}`。
- `GET  /assets/cmdb/impact`（`asset:topo:view`）：`entity_type,entity_id,direction(默认 down),depth(默认 2 / 硬上限 3，超限 **422**),rel_types[]` ⇒ `{root,affected[],count,truncated}`。
- **数据权限（US-03）**：拓扑/影响结果按当前用户**可见实体集**裁剪（与 `HostRepository.visible_entity_ids` 同源），越权节点不返回；**写路径** `POST/DELETE` 须校验调用者**同时可见 src 与 dst**，否则 **403**。

### 12.4 权限码 / flag / 迁移 / 边界
- **权限码**（**复用 `asset:` 命名空间，不新开 `cmdb:`**）：`asset:relation:list` / `asset:relation:add` / `asset:relation:del` / `asset:topo:view`（新增 4 点）。
- **feature flag**：`config_rule` 命名空间 **`feature.cmdb_topology`**（默认 False；与既有 `feature.*` 一致）。
- **迁移**：新增 **1** 迁移（`entity_relation` + 约束/索引），`down_revision=e1f2a3b4c5d7`，**保持单 head**；新 rev **入「禁落 live」集 C**（与 P3.1 同规；`LIVE_REV_ALLOWED` A/B 不变），三处 allow-set 锁 / 链计数随**实现批**同步（C 3→4、链 14→15）。
- **前端**：`/assets/cmdb/topology` 拓扑页 + 关系维护（`v-perm` 复用），由前端随批接入。
- **路径增量**：**URL 键 +4 → `len(paths)==133`**（`/assets/relations` GET+POST **共用 1 键**、`/assets/relations/{id}`、`/assets/cmdb/topology`、`/assets/cmdb/impact`）＝ **5 operations**；**`removed==[]`**，openapi 自动同步。
- **审计（R4）**：关系 `add/del` 由 **`AuditMiddleware` 自动写 `sys_audit_log`**（写请求全覆盖、**无需新代码**）；关系行另存 `created_by/ts`。
- **悬空边（无 FK，多态引用）**：删主机/分组时**应用层级联清理**其关系 ＋ 查询侧对缺失 id **防御性跳过**（`list` 过滤）。

### 12.5 与 §26 AIOps 的关系（避免双建）
- §26 AIOps 只读「拓扑」= **复用本 §12 的 `entity_relation`**；AIOps 若需新增节点类型（`service`/`app`/`ops_event` 等）**扩展 `*_type` 枚举与 `rel_type` 词表**，不另建表。
- AIOps 提案中架构列的 `entity_relation`(拓扑) **以本表为准**；AIOps 立项时**直接消费**。

## 13. 编排 Playbook（三期 P3-4：DAG 工作流）

> 承 §9：**复用一期 exec_task/审批/notify 原语**，在 Celery 之上做 DAG 调度器，**不引新框架**；flag 默认关。

### 13.1 能力
- **定义/版本**：Playbook ＝有向无环图（DAG），节点 `node_key`＋类型＋配置＋依赖；版本化（复刻 script/KB 语义：current_version 指针、append-only 版本、可回滚）。
- **运行状态机**：`workflow_run`＝`pending→running→(succeeded|failed|cancelled)`，running 内节点可 `waiting`（候审批/回调/依赖）。
- **调度**：节点入度满足才 ready；依赖表达 wait_for ＋ 分支（on_success/on_failure 边条件）；DAG 分支并行；**幂等/重入**（触发 Idempotency-Key、节点 attempt、断点续跑）。
- **复用**：`node_type=exec_task` **创建并等待一期 exec_task**；`manual_approval` **复用审批状态机**；`wait/callback/sleep` 为编排原语。**不复制**执行/审批逻辑。
- **控制**：取消传播（复用 exec stop）、超时收敛、失败按分支或整体 failed。
- **非目标**：不做图库/大屏；不做新调度框架。

### 13.2 数据模型（新增，add-only）
- `workflow`：name(unique), description, current_version, enabled, created_by, ts。
- `workflow_version`：workflow_id, version, **definition JSONB**（`nodes[{key,type∈{exec_task,manual_approval,wait,callback,sleep},config,depends_on[],on_success[],on_failure[]}]`）, editor_id, at（append-only）。
- `workflow_run`：workflow_id, workflow_version, status(pending|running|succeeded|failed|cancelled), trigger_type(manual|ticket|schedule|alert|release), trigger_ref JSONB, context JSONB, started_at/finished_at, error, created_by, ts。
- `workflow_node_run`：run_id, node_key, node_type, status(pending|running|succeeded|failed|skipped|waiting), **exec_task_id?**, **approval_id?**, attempt, output JSONB, error, started_at/finished_at。
- 约束：`(run_id,node_key)` 唯一、`(workflow_id,version)` 唯一；留痕 `sys_audit_log` ＋节点 output。

### 13.3 接口（REST + WS）
- `GET/POST /workflows`、`GET/PUT/DELETE /workflows/{id}`（被运行引用 409）。
- `POST/GET /workflows/{id}/versions`、`POST /workflows/{id}/rollback`。
- `POST /workflows/{id}/run` ⇒ `{run_id}`（幂等 Idempotency-Key）。
- `GET /workflow-runs`、`GET /workflow-runs/{id}`（**DAG 节点状态矩阵**）、`POST /workflow-runs/{id}/cancel|retry`。
- WS `/ws/workflow-runs/{id}`：节点状态实时推送（复刻 exec WS 帧 seq 防乱序）。
- 权限码：`workflow:list/add/edit/del/version/rollback/run/view/cancel`（9）；flag **`feature.workflow`**（默认 False）。
- paths ≈ **+6**；迁移 **+1**（4 表，rev 链在 P3-3 `f2a3b4c5d6e7` 之后、单 head）。

## 14. CI/CD 集成（三期 P3-5：发布编排段）

> 定位：**不自造 CI 引擎**；平台只做「**发布编排段**」——消费流水线产物 → 触发/记录发布 → **灰度/回滚** → 审计；**建在 §13 workflow 之上**（release ＝ 一个 `workflow_run` 编排 ＋ provider 回调节点）。flag 默认关。

### 14.1 能力
- **Provider 对接**：`gitlab|jenkins|generic`，配置化接入（密钥密文）；出站触发/拉取产物走 provider API，**测试用 stub/mock**。
- **入站事件**：`POST /cicd/webhooks/{provider}` 归一化「构建完成/产物就绪」事件（provider token 鉴权、**非 session**）；可触发 release 或 workflow。
- **发布编排**：release 状态机 `pending→deploying→canary→succeeded`（异常 `failed→rolled_back`）；灰度＝分批放量＋健康检查（复用 exec_task 部署）；回滚＝回退上一版本。
- **审计**：发布/灰度/回滚均记 `sys_audit_log`，关联 `workflow_run`/exec_task 证据。
- **边界（非目标）**：**不含源码→构建→测试**（属 GitLab CI/Jenkins）。

### 14.2 数据模型（新增，add-only）
- `cicd_provider`：type(gitlab|jenkins|generic), name, endpoint, config_enc(JSON 串，密钥逐值密文), enabled, status, last_heartbeat, created_by, ts。
- `release`：provider_id, app, version/artifact_ref, env(dev|test|prod), status, **workflow_run_id?**, target_host_ids JSONB, rolled_back_from?, created_by, ts。
- 产物契约：`artifact_manifest`（version/app/env/artifact_ref/checksum），入站事件与 release 共用。

### 14.3 接口（REST + inbound webhook）
- `GET/POST /cicd/providers`、`PUT/DELETE /cicd/providers/{id}`、`POST /cicd/providers/{id}/test`。
- `POST /cicd/webhooks/{provider}`（token 鉴权）。
- `GET/POST /releases`、`GET /releases/{id}`（状态/证据链）、`POST /releases/{id}/canary|promote|rollback|cancel`。
- 权限码：`cicd:provider:list/add/edit/del/test` ＋ `release:list/add/view/run/canary/promote/rollback/cancel`；flag **`feature.cicd`**（默认 False）。
- paths ≈ **+8**；迁移 **+1**（链在 P3-4 rev 之后、单 head）。
- 前端：`/cicd/providers`、`/releases`（列表/状态，不引图库）。

### 14.4 与 §13 / 批次关系
- release 编排**复用** §13 workflow（DAG/审批/exec_task 原语），**不重复造编排**；P3-5 只加 provider 接入＋发布语义＋灰度/回滚。
- 批次序：**P3-3 冻结 → P3-4 → P3-5**；各批独立锚 ＋ live F ＋ 三源互证。