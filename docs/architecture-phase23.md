# lark-plat 自动化运维平台 — 二期/三期架构设计 v3.0

版本: v3.0（草案，对齐需求 v1.2 待细化）  |  日期: 2026-09-08  |  作者: 架构师

> 承接 v2.1 终态（权威根 4309005）。本文档为二/三期新增能力的架构设计，全部模块对一期 MVP 采用 **add-only 扩展**：不修改既有 434 基线行为、alembic 保持单 head、新能力经 feature flag 可切。接口契约增量见 `api-design-v3.md`。

## 1. 范围界定

| 期 | 模块 | 对应需求 | 状态 |
|----|------|----------|------|
| 二期 | 文件分发 | FR-14/15（上传分发/回传） | 本设计 |
| 二期 | 监控告警 | FR-25/26（指标采集/告警规则/通知联动）+ 外部监控生态对接（Prometheus/ELK/SkyWalking，刘辉 D2 定方向 2026-09-08） | 本设计 |
| 二期 | 身份集成 | LDAP / OAuth2 SSO（对齐一期登录页预留形态） | 本设计 |
| 二期 | 执行器扩展 | SSH 直连降级（架构决策 2 预留位启用）+ Windows 执行器 | 本设计 |
| 三期 | 工单 | FR-27（运维工单流程） | 本设计 |
| 三期 | 知识库 | 知识沉淀（关联脚本/资产/工单） | 本设计 |
| 三期 | CI/CD 集成 + 编排 | 架构 §1 三期项 | 后续细化 |

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
- 告警规则：metric + op(=/</>/<=/>=) + value + duration(持续时长) + 生效范围(主机/分组) + 静默窗口 + 级别——规则作用于归一化事件，不区分自采/外部来源。
- 告警引擎（Celery beat）：周期扫描最近窗口指标/事件 → 评估触发 → **alert 生命周期 pending→firing→resolved** + **收敛（dedup/聚合同源重复）+ 升级（escalation 逐级提级）** → 复用 notify（场景 scene=alert_fire/alert_resolve）。
- 告警处置：列表/详情/确认(acknowledge)/恢复(resolve)/手动触发规则测试；告警历史可查。
- 实时推送：WS `/ws/monitor` 订阅指标/告警（帧协议权威见 api-design-v3.md §2；subscribe 范围服务端按 US-03 强制过滤）。

### 4.2 数据模型（表名遵循一期前缀惯例：`mon_*`；API 路由仍为 `/monitor/*`）
- `mon_metric_sample`：host_id, metric_name, value, ts（按日分区 + (host_id, metric_name, ts) 索引；raw 7d 后清理，聚合入 `mon_metric_daily`）。
- `mon_adapter`：name, direction(agent|inbound|outbound), kind(map: metric|alert|log|apm), type(prometheus|alertmanager|elk|skywalking|webhook), config(JSONB，endpoint/token/字段映射等，密钥类密文), enabled, created_by, updated_at。
- `mon_event_inbox`：归一化 MonEvent 入站（source, kind, entity, ts, value, severity, labels(JSONB), raw(JSONB), received_at）——规则评估前暂存/去重（按 source+event_id 幂等——外部 webhook/remote_write 可携带 event_id）。
- `mon_rule`：name, kind, metric_name, op, value, duration_sec, scope_type(host|group), scope_ids(JSONB), level(info|warning|critical), silence_sec, converge_sec(收敛窗口), escalate_levels(JSONB，逐级升级), enabled, notify_channel_ids(JSONB, 复用 notify), created_by。
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

- 收敛（dedup）：firing 后同源同键在 `converge_sec` 内重复命中只去重（transient suppressed），不重复 notify；升级由 `escalate_levels` 逐级提级，写 action=escalate。
- 并发/竞态：state_store 用 CAS 乐观锁（rule_id+entity+收敛键唯一）；超时未收到事件 → 自动 resolved（可配，默认 10min）；已触发告警保留原规则快照；from_status→to_status 非法转移拒绝（TRANSITIONS 白名单）。

## 5. 身份集成（LDAP / OAuth2 SSO）

### 5.1 能力
- 登录页多方式（一期已预留）：账号密码 / LDAP / OAuth2（如内部 IdP，可扩展）。
- LDAP：bind 认证（`provider bind_dn 模板 + search`），返回用户身份 → 本地用户按 `map_key(username|email|uid)` 匹配，可自动建档（`auto_provision` + 默认角色）或仅绑定既有用户。
- OAuth2：授权码模式（state 防 CSRF，redirect_uri 白名单），换取 profile → 同样映射/建档。
- 外部认证成功后统一发一期 JWT；本地密码用户与外部用户并存（`auth_source` 区分，互不干扰）；登出/刷新/权限/数据权限全复用。

### 5.2 数据模型（对 users 做 add-only 扩展）
- 新增独立表 `auth_provider`（type=ldap|oauth2, name, config(JSONB 密文部分), enabled）。
- `users` 新增可空列：`auth_source`（default 'local'）、`external_id`、`last_external_login_at`——mvp 已冻结，采用 **additive migration**（nullable 列 + default）。
- `config_rule` 扩展命名空间 `sso.auto_provision`, `sso.default_role_codes`（JSONB 配置，不新增表）。

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
- `ticket`：title, category, priority, status, requester_id, assignee_id, team_id(可选), description, sla_due_at, resolved_at/closed_at, created_at。
- `ticket_comment`：ticket_id, author_id, content, at——append-only。
- `ticket_attachment`：ticket_id, file_id(复用 file_package 存储), at。
- `ticket_ref`：ticket_id, ref_type(exec_task|approval|asset_host|schedule|kb_article), ref_id。

## 8. 知识库（三期）

### 8.1 能力
- 文章 CRUD + 分类/标签 + 版本历史（复刻 script 版本语义）+ 可见级（public/internal/classified，内附和 switch 到 RBAC 角色/主机组）。
- 全文检索（Postgres FTS，中文分词扩展后续可选）；关联引用（文章↔脚本/资产/工单）。
- 净化：指令类内容高亮与一键转执行（引用脚本时校验权限）。

### 8.2 数据模型
- `kb_article`：title, category_id, visibility, current_version, author_id, content(JSONB 或 text), created_at/updated_at。
- `kb_article_version`：article_id, version, content, editor_id, at。
- `kb_category` / `kb_article_tag`（tag 复用一期 tag 枚举思路）。

## 9. CI/CD 集成 + 编排（三期，先立架构）

- **Pipeline 抽象**：`pipeline → stage[] → step[]`；step 可触发 exec_task（复用执行链路）、自定义回调、等待人工审批（复用审批链路）。
- **编排**：步骤间依赖 DAG（wait_for/on_success/on_failure），在 Celery 之上实现工作流调度器（`workflow` 服务 + `workflow_run` 状态机），不做新框架（避免过度设计）。
- 与工单/知识库/告警联动（发布变更工单引出流水线等）作为三期后续细化内容，本版只立概念与边界。

## 10. 非功能与兼容红线

- **不破坏 234 基线**：全部新功能独立模块/新表/新路由；既有行为零改动；新增测试合计在新文件（锁定稿模式）。
- **alembic 单 head**：二期/三期迁移按批次单链推进；`users` 仅在必要时加 nullable 列。
- **feature flag**：`config_rule` 命名空间 `feature.transfer/monitor/sso/terminal_ssh` 控制开关，默认按批次上线。
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
| P3-3 | CI/CD + 编排 | P3-1 | 另立项细化 |

每批走既有流程：需求细化 → 本席设计定稿 → 开发 → 评审 → 单测 → 集成 live → 需求允收。