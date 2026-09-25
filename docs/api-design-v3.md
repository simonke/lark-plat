# lark-plat 自动化运维平台 — 二/三期接口契约增量 v3.0

版本: v3.0（草案，对齐架构 v3.0）  |  日期: 2026-09-08  |  作者: 架构师

> 本文件为 `api-design.md` v2.1 的增量补丁。通用约定（base path、认证、信封、分页、错误码、snake_case、时间）沿用 v2.1，不重复。所有新路由权限点前缀新增 permission 种子（随功能批次注入）。全部新增接口走 `Result{code,message,data}` / `PageVO{list,total,page,size}`。

## 1. 文件分发（P2-1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /transfer/packages | multipart 上传（files[]）→ {package_id, name?, items:[{path,size,sha256}]} |
| GET | /transfer/packages | 分页列表：name/时间范围 → PageVO{list,total,page,size} |
| GET | /transfer/packages/{id} | 包详情（files 校验和清单） |
| DELETE | /transfer/packages/{id} | 删除上传包（被任务引用 409） |
| POST | /transfer/tasks | {mode:push/pull, package_id?, source_host_path?, source_host_id?, target_path, host_ids, overwrite, verify, limit_mbps?} → {id, task_no, status, pending} |
| GET | /transfer/tasks | 分页：mode/status/时间范围 |
| GET | /transfer/tasks/mine | viewer 日志入口：按 transfer:task:log 门禁枚举可读任务（非 admin 仅 created_by=user.id），复用 task 输出形状（task_id + host_ids 资产 id 零漂移）+ hosts:[{id, hostname}]（TransferHost 行 id，两 id 空间显式区分，seq1724 方案B） |
| GET | /transfer/tasks/{id} | 详情（hosts 汇总 + 校验状态） |
| GET | /transfer/tasks/{id}/hosts/{transfer_host_id}/logs | ?after_seq=&size= 历史补拉（同 exec 语义） |
| GET | /transfer/tasks/{id}/hosts/{transfer_host_id}/ws-token | WS 握手 token（绑定 transfer_host_id, 5min） |
| POST | /transfer/tasks/{id}/stop | 终止 |
| POST | /transfer/tasks/{id}/hosts/{transfer_host_id}/retry | 单主机重试（failed/verify_failed） |
| GET | /transfer/tasks/{id}/stats | {total,pending,transferring,verifying,verify_failed,success,failed} |

### WS 实时进度（复刻 exec 模式）
```
WSS /api/v1/ws/transfer/{transfer_host_id}?token=<5minJWT>
S→C: {"type":"log","data":{"seq":1,"level":"info","content":"sha256 校验通过"...}}
C→S: {"type":"stop"} | {"type":"ping"}
```

请求示例（push）：
```json
{ "mode": "push", "package_id": 7, "target_path": "/opt/pkg/app", "host_ids": [1,2,3], "overwrite": 1, "verify": 1 }
```
响应 data：
```json
{ "id": 12, "task_no": "TF-20260908-001", "status": "processing", "pending": 3 }
```

字段形状（v1.1，落地实现为权威）：
- 包列表项 `TransferPackageOut`：`file_count`/`total_size`（列表不含 items）；详情 `GET /packages/{id}` 返回 `TransferPackageDetail`（含 items[{path,size,sha256}]）；上传返回 `{package_id, items}`
- `overwrite`/`verify` 为 0|1（int，JSON 宽进窄出，非 bool）
- `host_ids` 请求为 `number[]`；任务出参 `TransferTaskOut.host_ids` 透传 JSONB `{ids:[...]}` → `Record<string,unknown>|null`
- 任务创建返回 `{id, task_no, status, pending}`（非全量 TaskOut）
- 主机出参 `TransferHostOut` 含 `channel`（agent/ssh/degraded）
- stats 归并口径（v1.2）：`failed` = 终态非成功计数（`failed/verify_failed` 失败 + `degraded/canceled` 不可用）；`transferring` = `transferring+pulling`；七键守恒（求和 = total）。任务聚合判定与 stats 数字归并两级语义分家：degraded 非失败只约束聚合（全 degraded=partial），stats 层面仍归入 failed 保持守恒

两级状态枚举（权威，v1.1，聚合规则 v1.2）：
- **host 级**：`pending|pulling|transferring|verifying|success|failed|verify_failed|degraded|canceled`（含 pulling=拉取中；verify_failed 可 retry；degraded=通道不可用，非失败不计硬失败）
- **task 级**：`processing|success|partial|failed|canceled`（聚合：存在 success → success/partial（全 success=success，其余=partial）；无 success 时 → 无真失败则 partial（如全 degraded）否则 failed）

权限点：transfer:package:list/add/del / transfer:task:list/run/stop/retry/log（「文件分发」菜单 `transfer:package:list` path=/transfer/tasks，children 含 task:list 共 7 按钮）

## 2. 监控告警（P2-2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /monitor/metrics | 时序查询：entity_ids/group_id/metric_name/start/end/agg(5m/1h/1d) → {points:[{entity_id,ts,value}]}（agg 按 (entity_id,bucket) 分组） |
| GET | /monitor/metrics/current | 最新心跳值（主机详情页展示） |
| POST | /monitor/rules | {name, event_kind, metric_name, condition_operator, condition_threshold, condition_duration_seconds, scope_type, scope_ids:list[str], level, cooldown_seconds, converge_sec, escalate_levels, notify_channel_ids} |
| GET | /monitor/rules | 分页 |
| PUT | /monitor/rules/{id} | 编辑 |
| DELETE | /monitor/rules/{id} | 删除 |
| POST | /monitor/rules/{id}/status | {enabled} |
| POST | /monitor/rules/{id}/test | 立即试算一次规则（对当前最近窗口） |
| GET | /monitor/alerts | 分页：rule_id/status(pending/firing/acknowledged/resolved)/entity/时间范围 |
| GET | /monitor/alerts/{id} | 详情（时间线 events） |
| POST | /monitor/alerts/{id}/acknowledge | {remark} 确认（可多次，append-only） |
| POST | /monitor/alerts/{id}/resolve | {remark} 手动恢复 |
| GET | /monitor/alerts/{id}/events | 事件时间线 |
| POST | /monitor/adapters | {name, type[prometheus/alertmanager/elk/skywalking], endpoint, config{...}, enabled}（密钥字段密文） |
| GET | /monitor/adapters | 列表 |
| PUT | /monitor/adapters/{id} | 编辑（不传则保留原密文） |
| DELETE | /monitor/adapters/{id} | 删除 |
| POST | /monitor/adapters/{id}/status | 启停 |
| POST | /monitor/adapters/{id}/test | 连通性试测（remote_write/端点探测/webhook 校验） |
| POST | /monitor/ingest/{adapter_id} | 免认证 webhook/remote_write 入站：外部告警/指标推送归一化（支持 Alertmanager/webhook 通用 JSON），按 source+event_id 幂等 |
| GET | /monitor/events | 归一化 MonEvent 流（分页：source/kind/severity/时间范围） |
| GET | /monitor/events/{id} | 事件详情（含 raw 原始报文） |
| GET | /monitor/ws-token | WS 握手 token（绑定用户在可见主机范围内的订阅 JWT，5min，同 exec 语义） |

请求示例（规则，按 MonRuleCreate 对齐）：
```json
{ "name": "CPU 高负载", "event_kind": "metric", "metric_name": "cpu",
  "condition_operator": ">", "condition_threshold": 90, "condition_duration_seconds": 300,
  "scope_type": "host", "scope_ids": ["h1"], "level": "warning", "cooldown_seconds": 3600,
  "converge_sec": 600, "escalate_levels": ["warning","critical"],
  "notify_channel_ids": [1,2] }
```

请求示例（adapter，按 MonAdapterCreate 对齐，prometheus remote_write）：
```json
{ "name": "it-prometheus", "type": "prometheus", "endpoint": "http://prometheus:9090/api/v1/write",
  "config": {"remote_write": true}, "enabled": 1 }
```

请求示例（ingest，归一化 MonEvent 推送）：
```json
POST /monitor/ingest/{adapter_id}
{ "source": "prometheus", "kind": "metric", "metric_name": "cpu",
  "entity": {"entity_type": "host", "entity_id": "web-01", "entity_name": "web-01"},
  "value": 95.2, "severity": "warning",
  "ts": "2026-09-11T12:00:00Z", "event_id": "prom-web01-1726056000" }
```

响应 data（成功，Result 裹层）：
```json
{ "accepted": 1, "rejected": 0, "adapter_id": 7 }
```

响应 data（不支持的 payload 形状 → dead-letter）：
```json
{ "accepted": 0, "rejected": 1, "adapter_id": 7 }
```

> 幂等语义：按 `source + event_id` 去重（`event_key = source:event_id`），同一 event_id 再次入站 accepted=1、dedup=True，不重复落库。入站格式：规范 MonEvent（必含 source/kind/entity/ts）；外部格式（alertmanager `{status,alerts[]}`、prometheus remote_write、elk、skywalking）由 adapter 归一化处理。

### WS `/ws/monitor` 实时推送帧协议（权威）
握手：`GET /monitor/ws-token` → 绑定 JWT（5min），`WSS /api/v1/ws/monitor?token=<jwt>`。订阅范围服务端按 US-03 强制过滤（不可越权订阅）。
```
S→C:
  {"type":"hello","data":{"subscribed":"all|hosts|group","ids":[...]}}   # 握手确认
  {"type":"alert","data":MonAlertOut}                                    # 告警状态/事件推送(fire/acknowledge/escalate/resolve)
  {"type":"metric","data":{"host_id":1,"metric_name":"cpu","value":78.5,"ts":"ISO8601"}}  # 实时指标(可选订阅)
  {"type":"pong"}
C→S:
  {"type":"subscribe","data":{"scope":"hosts","ids":[1,2]}}              # 订阅范围(重订阅)
  {"type":"ping"}
```
`MonAlertOut = {id, rule_id, rule_name, entity{entity_type,entity_id,entity_name}, source, status, severity, last_value, fired_at, resolved_at, action(fire|acknowledge|escalate|resolve|suppress), ts}`。

权限点：monitor:metric:view / monitor:rule:list/add/edit/del/status/test / monitor:alert:list/view/ack/resolve

> 变更注记（add-only，裁定 L seq1788）：原 `/monitor/metrics` 查询参数 `host_ids` 更正为 `entity_ids`；`entity_ids` 为归一化 entity id 列表（字符串），非资产主键，可为 host/app/service。

> 变更注记（add-only，裁定 T seq1810）：`agg` 模式下 points 按 `(entity_id,bucket)` 分组，每点含 `entity_id`（多实体不混合成单序列，前端 `buildMetricSeries` 据此拆分）；另含 `bucket/avg/max/min/count`，并保留 `ts=bucket`、`value=avg` 兼容字段。

## 3. 身份集成 LDAP/OAuth（P2-3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /auth/providers | 登录页可变方式列表 {code,type,name}（含 local） |
| POST | /auth/providers | {name,type[ldap/oauth2],config{...},enabled}（密钥字段加密存储） |
| PUT | /auth/providers/{id} | 编辑（不传则保留原密文） |
| DELETE | /auth/providers/{id} | 删除 |
| PUT | /auth/providers/{id}/status | 启停 |
| POST | /auth/providers/{id}/test | 连通性/凭据试测（ldap: bind test；oauth2: token 端点探测） |
| GET | /auth/oauth/{provider}/login | 302 → IdP（state 落 Redis 5min） |
| GET | /auth/oauth/{provider}/callback | IdP 回调 → 映射/建档 → 签发 JWT 对（302 回前端带 token） |
| POST | /auth/ldap/login | {username,password} LDAP bind 登录 → JWT 对（与本地登录同响应） |

> `GET /auth/providers`（R1 角色变体，add-only 注记）：**匿名 200 canonical＝恰 `{code,type,name}`**（不得含 `id/enabled/config_mask/created_at/config_enc`）；**持 `system:auth:provider` 时＝管理超集 ⊇ `{id,code,type,name,enabled,config_mask,created_at}`**（同 path 角色变体、键集断言；禁明文 `config`/`config_enc`/`login_path`）。

OAuth2 回调成功响应（JSON 模式可选）：`{access_token,refresh_token,user{id,username,real_name,roles}}`（与 POST /auth/login 同构）。

> 变更注记（add-only，P2-ID §3-v2.1 裁定 seq2090/2092）：
> - **LDAP 必填**＝`server_uri, bind_dn, bind_dn_template, base_dn, password(密钥)`；**可选**＝`filter, map_key, auto_provision, default_role_codes, roles_claim`。`/test`＝`bind_dn`+`password` 真实服务账号 bind；登录＝`bind_dn_template.format(username)`＋用户密码。**旧键 `bind_password` 已删除**。
> - **OAuth2 必填**＝`authorization_endpoint, token_endpoint, client_id, client_secret(密钥), redirect_uri`；**可选**＝`userinfo_endpoint, scope, map_key, roles_claim, auto_provision, default_role_codes`。**旧键 `authorize_url/token_url/userinfo_url` 已替换**。
> - **存储/掩码**：密钥值 `"enc:"+encrypt_secret(v)` 存入 `config_enc`（列存 JSON）、非密钥原样；`config_mask` 仅掩码密钥值（`ab******yz`/`****`），非密钥可见、密钥不回显明文；`PUT` 未传键＝保留、传含 `*` 掩码串＝保原密文。
> - **错误码**：校验类（必填缺失/非法 `type`/未知角色码）＝**422**；业务冲突（`code` 重复、`sso` 未启用、`state` 失效/重放）＝**400**。
> - `GET /auth/oauth/{provider}/login` 默认 **302**、`?mode=json` 返回 JSON；`POST /auth/providers/{id}/test` → `{ok,latency_ms,error_message}`。

LDAP config 示例：
```json
{ "server_uri": "ldaps://ldap.example.com:636", "bind_dn": "cn=svc,ou=services,dc=example,dc=com",
  "bind_dn_template": "uid={username},ou=people,dc=example,dc=com",
  "base_dn": "ou=people,dc=example,dc=com", "filter": "(objectClass=person)", "map_key": "email",
  "password": "enc:...", "auto_provision": true, "default_role_codes": ["ops"], "roles_claim": "groups" }
```

OAuth2 config 示例：
```json
{ "authorization_endpoint": "https://idp.example.com/oauth2/authorize", "token_endpoint": "https://idp.example.com/oauth2/token",
  "userinfo_endpoint": "https://idp.example.com/oauth2/userinfo", "client_id": "...", "client_secret": "enc:...",
  "redirect_uri": "{backend_base}/api/v1/auth/oauth/{code}/callback", "scope": "openid profile email",
  "map_key": "sub", "roles_claim": "groups", "auto_provision": true, "default_role_codes": ["ops"] }
```

权限点：system:auth:provider 系列（复用 system:user 管理面）

## 4. 执行器扩展（P2-4）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /assets/hosts/{id}/executors | 可用执行器 {available:[agent,ssh], active, reason}（评估降级条件） |
| PUT | /assets/hosts/{id}/connector | {connector:[agent/ssh]} 手动切换（管理员） |

Agent 帧扩展（一期 §12 追加，向后兼容）：
| 方向 | type | data |
|------|------|------|
| S→C | file_send | {transfer_host_id, file_item{path,size,sha256,chunk_size}, offset} |
| C→S | file_chunk_ack | {transfer_host_id, offset, bytes, crc32}（若校验失败协商重发） |
| S→C | file_verify | {transfer_host_id, path, sha256} |
| C→S | file_result | {transfer_host_id, status, sha256, error} |
| S→C | file_fetch | {transfer_host_id, path, offset}（pull 模式） |
| C→S | metric | {items:[]}（批量补推，字段同 heartbeat.metrics） |

SSH/Windows 执行器对前端无新增接口（复用 exec/* 与 /terminals），仅行为差异；主机详情展示 connector/executor 标识。

权限点：asset:host:executor（复用 asset:host:edit）

## 5. 工单（P3-1）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /tickets | 分页：`ticket_no`/category/status/priority/requester_id/assignee_id/时间范围 |
| POST | /tickets | {title,category,priority,description,assignee_id?,host_ids?,due_at?} |
| GET | /tickets/{id} | 详情（refs + comments + attachments） |
| PUT | /tickets/{id} | 编辑（未受理前） |
| POST | /tickets/{id}/assign | {assignee_id} |
| POST | /tickets/{id}/accept | 受理 |
| POST | /tickets/{id}/process | 处理中 |
| POST | /tickets/{id}/done | {remark, exec_task_id?} 完成（可关联执行证据） |
| POST | /tickets/{id}/close | 关闭 |
| POST | /tickets/{id}/reopen | 重新打开 |
| POST | /tickets/{id}/cancel | 取消 |
| POST | /tickets/{id}/comments | {content} |
| POST | /tickets/{id}/attachments | multipart files[] |
| POST | /tickets/{id}/refs | {ref_type,ref_id} 关联执行/审批/资产/计划/脚本/知识 |

输出：`TicketOut`（create/detail/list 同值）含**只读** `ticket_no`（`TK-YYYYMMDD-NNN`，全局唯一、不可变；不入建单/编辑入参）。

请求示例（建单）：
```json
{ "title": "生产 nginx 高负载处理", "category": "incident", "priority": "high",
  "description": "P95 延迟升高，需排查", "assignee_id": 5, "host_ids": [3] }
```

权限点：ticket:list/create/edit/assign/accept/process/done/close/reopen/cancel/comment/attachment/ref（13 码，按状态机校验）

## 6. 知识库（P3-2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /kb/articles | 分页：keyword/category_id/tag/visibility |
| POST | /kb/articles | {title,category_id,visibility[public/internal/classified],content} |
| GET | /kb/articles/{id} | 详情（current_version） |
| PUT | /kb/articles/{id} | 编辑 → 新版本 |
| DELETE | /kb/articles/{id} | 删除（被工单引用需确认） |
| GET | /kb/articles/{id}/versions | 版本列表 |
| GET | /kb/articles/{id}/versions/{version} | 某版本内容 |
| POST | /kb/articles/{id}/rollback | {version} 回滚 |
| GET | /kb/categories | 分类树 |
| POST | /kb/categories | {name,parent_id?} |
| PUT | /kb/categories/{id} | 编辑 |
| DELETE | /kb/categories/{id} | 删除（有文章拒绝） |
| GET | /kb/search | ?q= 全文检索（同页签名） |

权限点：kb:article:list/add/edit/del/version/rollback / kb:category:list/add/edit/del / kb:search
（classified 可见级叠加主机组/RBAC 校验，复用一期数据权限中间件）

## 7. 三期契约：CMDB 深化 / 编排 / CI-CD（P3-3/4/5）

### 7.1 CMDB 深化（P3-3）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /assets/relations | 列表（筛选 src/dst/rel_type）/ 创建（**幂等**） |
| DELETE | /assets/relations/{relation_id} | 删除（`{id}` 为速记别名；canonical=`{relation_id}`） |
| GET | /assets/cmdb/topology | 邻域 `{nodes[{type,id,label,role}],edges[{src,dst,rel_type}]}`；depth 默认 2 / 硬上限 3（超限 **422**） |
| GET | /assets/cmdb/impact | 下游可达集 `{root,affected[],count}` |

权限点：`asset:relation:list/add/del` / `asset:topo:view`。表 **`entity_relation`**（§26 AIOps 复用同表）。

### 7.2 编排 Playbook（P3-4）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /workflows | 列表/创建 |
| GET/PUT/DELETE | /workflows/{id} | 详情/编辑/删除（被运行引用 409） |
| POST/GET | /workflows/{id}/versions | 新版本 / 版本列表 |
| POST | /workflows/{id}/rollback | 回滚 |
| POST | /workflows/{id}/run | 触发 ⇒ {run_id}（Idempotency-Key） |
| GET | /workflow-runs · /workflow-runs/{id} | 运行历史 / 详情（DAG 节点状态） |
| POST | /workflow-runs/{id}/cancel · /retry | 取消 / 重试 |

WS `/ws/workflow-runs/{id}`。权限点：`workflow:list/add/edit/del/version/rollback/run/view/cancel`。

### 7.3 CI/CD 集成（P3-5）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /cicd/providers | 列表/创建 |
| PUT/DELETE | /cicd/providers/{id} · POST /cicd/providers/{id}/test | 编辑/删除/连通测试 |
| POST | /cicd/webhooks/{provider} | 入站事件（**token 鉴权、非 session**） |
| GET/POST | /releases | 列表 / 创建发布编排 |
| GET | /releases/{id} | 详情（状态/证据链） |
| POST | /releases/{id}/canary · /promote · /rollback · /cancel | 灰度/放量/回滚/取消 |

权限点：`cicd:provider:list/add/edit/del/test` / `release:list/add/view/canary/promote/rollback/cancel`。

> 本节取代旧版 §7「/pipelines」骨架：P3-3 拆为 **CMDB 深化 / 编排 Playbook / CI-CD 集成** 三段，承 @刘辉 2026-09-24 立项。

## 8. 批次落地顺序（与 architecture-phase23.md §11 对齐）

- P2-1 文件分发 → api §1 + WS + Agent 帧 file_*
- P2-2 监控告警 → api §2 + Agent 帧 metric
- P2-3 SSO → api §3（复用 auth）
- P2-4 执行器扩展 → api §4（无新前端路由，仅行为）
- P3-1 工单 → api §5
- P3-2 知识库 → api §6
- P3-3 CMDB 深化 → api §7.1（表 `entity_relation`）
- P3-4 编排 Playbook → api §7.2（`/workflows` + `/workflow-runs`）
- P3-5 CI/CD 集成 → api §7.3（`/cicd/*` + `/releases`）

> 全部新增端点注册遵循一期实现注意：静态段路由先于 `{id}` 参数段注册（如 `/transfer/tasks/stats` 先于 `/transfer/tasks/{id}`）。