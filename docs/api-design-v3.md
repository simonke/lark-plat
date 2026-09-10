# lark-plat 自动化运维平台 — 二/三期接口契约增量 v3.0

版本: v3.0（草案，对齐架构 v3.0）  |  日期: 2026-09-08  |  作者: 架构师

> 本文件为 `api-design.md` v2.1 的增量补丁。通用约定（base path、认证、信封、分页、错误码、snake_case、时间）沿用 v2.1，不重复。所有新路由权限点前缀新增 permission 种子（随功能批次注入）。全部新增接口走 `Result{code,message,data}` / `PageVO{list,total,page,size}`。

## 1. 文件分发（P2-1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /transfer/packages | multipart 上传（files[]）→ {package_id, items:[{path,size,sha256}]} |
| DELETE | /transfer/packages/{id} | 删除上传包（被任务引用 409） |
| GET | /transfer/packages/{id} | 包详情（files 校验和清单） |
| POST | /transfer/tasks | {mode:push/pull, package_id?, source_host_path?, target_path, host_ids, overwrite, verify, limit_mbps?} → {id, task_no} |
| GET | /transfer/tasks | 分页：mode/status/时间范围 |
| GET | /transfer/tasks/{id} | 详情（hosts 汇总 + 校验状态） |
| GET | /transfer/tasks/{id}/hosts/{transfer_host_id}/logs | ?after_seq=&size= 历史补拉（同 exec 语义） |
| GET | /transfer/tasks/{id}/hosts/{transfer_host_id}/ws-token | WS 握手 token（绑定 transfer_host_id, 5min） |
| POST | /transfer/tasks/{id}/stop | 终止 |
| POST | /transfer/tasks/{id}/hosts/{transfer_host_id}/retry | 单主机重试（failed/verify_failed） |
| GET | /transfer/tasks/{id}/stats | {total,pending,transferring,verifying,success,failed} |

### WS 实时进度（复刻 exec 模式）
```
WSS /api/v1/ws/transfer/{transfer_host_id}?token=<5minJWT>
S→C: {"type":"log","data":{"seq":1,"level":"info","content":"sha256 校验通过"...}}
C→S: {"type":"stop"} | {"type":"ping"}
```

请求示例（push）：
```json
{ "mode": "push", "package_id": 7, "target_path": "/opt/pkg/app", "host_ids": [1,2,3], "overwrite": true, "verify": true }
```
响应 data：
```json
{ "id": 12, "task_no": "TF-20260908-001", "status": "processing", "pending": 3 }
```

权限点：transfer:package:list/add/del / transfer:task:list/run/stop/retry/log

## 2. 监控告警（P2-2）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /monitor/metrics | 时序查询：host_ids/group_id/metric_name/start/end/agg(5m/1h/1d) → {points:[{ts,value}]} |
| GET | /monitor/metrics/current | 最新心跳值（主机详情页展示） |
| POST | /monitor/rules | {kind, name, metric_name, op, value, duration_sec, scope_type, scope_ids, level, silence_sec, converge_sec, escalate_levels, notify_channel_ids} |
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
| POST | /monitor/adapters | {name,direction,kind,type[prometheus/alertmanager/elk/skywalking/webhook],config{...},enabled}（密钥字段密文） |
| GET | /monitor/adapters | 列表 |
| PUT | /monitor/adapters/{id} | 编辑（不传则保留原密文） |
| DELETE | /monitor/adapters/{id} | 删除 |
| POST | /monitor/adapters/{id}/status | 启停 |
| POST | /monitor/adapters/{id}/test | 连通性试测（remote_write/端点探测/webhook 校验） |
| POST | /monitor/ingest/{adapter_id} | 免认证 webhook/remote_write 入站：外部告警/指标推送归一化（支持 Alertmanager/webhook 通用 JSON），按 source+event_id 幂等 |
| GET | /monitor/events | 归一化 MonEvent 流（分页：source/kind/severity/时间范围） |
| GET | /monitor/events/{id} | 事件详情（含 raw 原始报文） |
| GET | /monitor/ws-token | WS 握手 token（绑定用户在可见主机范围内的订阅 JWT，5min，同 exec 语义） |

请求示例（规则）：
```json
{ "kind": "metric", "name": "CPU 高负载", "metric_name": "cpu", "op": ">", "value": 90, "duration_sec": 300,
  "scope_type": "group", "scope_ids": [3], "level": "warning", "silence_sec": 3600,
  "converge_sec": 600, "escalate_levels": ["warning","critical"],
  "notify_channel_ids": [1,2] }
```

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

OAuth2 回调成功响应（JSON 模式可选）：`{access_token,refresh_token,user{id,username,real_name,roles}}`（与 POST /auth/login 同构）。

LDAP provider config（示例，密钥类密文）：
```json
{ "server_uri": "ldaps://ldap.example.com:636", "bind_dn_template": "uid={username},ou=people,dc=example,dc=com",
  "base_dn": "ou=people,dc=example,dc=com", "filter": "(objectClass=person)", "map_key": "email",
  "password": "enc:..." , "auto_provision": true, "default_role_codes": ["ops"] }
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
| GET | /tickets | 分页：category/status/priority/requester_id/assignee_id/时间范围 |
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
| POST | /tickets/{id}/refs | {ref_type,ref_id} 关联执行/审批/资产/脚本/知识 |

请求示例（建单）：
```json
{ "title": "生产 nginx 高负载处理", "category": "incident", "priority": "high",
  "description": "P95 延迟升高，需排查", "assignee_id": 5, "host_ids": [3] }
```

权限点：ticket:list/create/edit/assign/accept/process/done/close/reopen/cancel/comment/attachment（按状态机校验）

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

## 7. CI/CD + 编排（P3-3，先立契约骨架）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /pipelines | {name,stages:[{name,steps:[{type:exec_task|manual_approval|callback, config}]}]} |
| GET | /pipelines | 分页 |
| PUT | /pipelines/{id} | 编辑 |
| DELETE | /pipelines/{id} | 删除（历史运行引用 409） |
| POST | /pipelines/{id}/run | 手动触发 → {run_id} |
| GET | /pipelines/{id}/runs | 运行历史 |
| GET | /pipelines/{id}/runs/{run_id} | 运行详情（DAG 节点状态） |
| POST | /pipelines/{id}/runs/{run_id}/stop | 中止 |

权限点：pipeline:list/add/edit/del/run/view 【三期细化】

## 8. 批次落地顺序（与 architecture-phase23.md §11 对齐）

- P2-1 文件分发 → api §1 + WS + Agent 帧 file_*
- P2-2 监控告警 → api §2 + Agent 帧 metric
- P2-3 SSO → api §3（复用 auth）
- P2-4 执行器扩展 → api §4（无新前端路由，仅行为）
- P3-1 工单 → api §5
- P3-2 知识库 → api §6
- P3-3 CI/CD+编排 → api §7（三期细化）

> 全部新增端点注册遵循一期实现注意：静态段路由先于 `{id}` 参数段注册（如 `/transfer/tasks/stats` 先于 `/transfer/tasks/{id}`）。