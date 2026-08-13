# lark-plat 自动化运维平台 — 接口设计 v2.1（契约）

版本: v2.1（对齐需求 v1.1）  |  日期: 2026-08-12  |  作者: 架构师

> 本文件为前后端/Agent 唯一接口契约。后端以 FastAPI 产出 OpenAPI（`/openapi.json`、`/docs`），前端据此生成 TS 类型，保证字段强一致。

## 1. 通用约定

- Base path：`/api/v1`；WebSocket 路径见 §5/§6。
- 认证：`Authorization: Bearer <access_token>`；Agent 用 `X-Agent-Token`。
- 字段命名：JSON 统一 **snake_case**。
- 统一响应：
  ```json
  { "code": 0, "message": "ok", "data": {} }
  ```
- 分页：`?page=1&size=10` → data：`{ "list": [], "total": 0, "page": 1, "size": 10 }`。
- 时间：ISO8601（`2026-08-12T18:00:00+08:00`）。
- 错误码：
  | code | 含义 |
  |------|------|
  | 0 | 成功 |
  | 400 | 参数校验失败（message 含字段） |
  | 401 | 未认证/Token 失效 |
  | 403 | 无权限（含主机组数据权限） |
  | 404 | 资源不存在 |
  | 409 | 冲突/重复提交/并发冲突 |
  | 422 | Pydantic 校验（FastAPI 默认） |
  | 429 | 触发限速/并发上限 |
  | 500 | 服务器错误 |
  | 1001 | 业务错误（message 说明，如"需审批"） |

## 2. 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /auth/login | {username,password} → {access_token,refresh_token,user{id,username,real_name,roles}} |
| POST | /auth/refresh | {refresh_token} → 新 token 对 |
| POST | /auth/logout | 登出 |
| GET | /auth/me | {user, permissions:[codes], visible_group_ids} |
| PUT | /auth/password | {old_password,new_password} |

## 3. 系统管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /system/users | 分页：username/real_name/status/role_id |
| POST | /system/users | {username,password,real_name,phone,email,role_ids} |
| PUT | /system/users/{id} | 编辑 |
| DELETE | /system/users/{id} | 删除 |
| PUT | /system/users/{id}/roles | {role_ids} |
| PUT | /system/users/{id}/status | {status} |
| PUT | /system/users/{id}/password | {password} 重置 |
| GET | /system/roles | 列表 |
| POST | /system/roles | {code,name,remark} |
| PUT | /system/roles/{id} | 编辑 |
| DELETE | /system/roles/{id} | 删除 |
| PUT | /system/roles/{id}/permissions | {permission_ids} |
| PUT | /system/roles/{id}/groups | {group_ids} 数据权限（可见主机组） |
| GET | /system/permissions | 权限点树 |
| GET | /system/audit-logs | 分页：module/action/username/ip/时间范围 |
| GET | /system/audit-logs/{id} | 详情（含 params，命令回放入口） |
| GET | /system/audit-logs/export | CSV 导出 |

## 4. 资产管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /assets/hosts | 分页：hostname/ip/os_type/group_id/env/tag/status/connector |
| GET | /assets/hosts/{id} | 详情（含 tags/connector/credential mask） |
| POST | /assets/hosts | {hostname,ip,os_type,os_version,group_id,env,tags,connector,sensitivity_level,remark} |
| PUT | /assets/hosts/{id} | 编辑 |
| DELETE | /assets/hosts/{id} | 删除（被任务/定时引用则 409） |
| POST | /assets/hosts/import | multipart CSV → {success,failed:[{row,error}]} |
| GET | /assets/hosts/export | CSV 下载 |
| POST | /assets/hosts/{id}/conn | 连通性检测 → {ok,latency_ms,detail} |
| GET | /assets/groups/tree | 分组树 |
| POST | /assets/groups | {parent_id,name} |
| PUT | /assets/groups/{id} | 编辑 |
| DELETE | /assets/groups/{id} | 删除（有子组/主机拒绝） |
| GET | /assets/hosts/stats | {total,online,offline,by_env}（按可见组） |
| GET | /assets/credentials | 凭据列表（mask） |
| POST | /assets/credentials | {host_id,type[password/key],username,secret,key,passphrase} |
| PUT | /assets/credentials/{id} | 编辑（不传则保留原密文） |
| DELETE | /assets/credentials/{id} | 删除 |
| GET | /assets/options | 下拉数据（分组树+主机名+环境枚举），供前端选择器 |

数据权限：所有 hosts/credentials 查询与操作按当前用户可见主机组过滤，越组返回 403/404。

## 5. 命令执行（核心）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /exec/tasks | 分页：task_no/name/status/kind/时间范围 |
| GET | /exec/tasks/{id} | 详情（含 hosts[] 汇总、approval 状态、sensitive_flag） |
| POST | /exec/tasks | 创建并（无需审批时）执行，见下方示例 |
| POST | /exec/tasks/{id}/stop | 终止（校验权限+状态） |
| POST | /exec/tasks/{id}/retry | 重试（仅 failed/timed_out/canceled） |
| GET | /exec/tasks/{id}/hosts/{task_host_id}/logs | ?after_seq=&size= → {list:[{seq,level,content,created_at}], next_seq} 历史补拉 |
| GET | /exec/tasks/{id}/hosts/{task_host_id}/ws-token | 续期：返回新的 5min WS 握手 token（access token 鉴权，校验主机可见） |
| GET | /exec/tasks/{id}/stats | {total,pending,running,success,failed,timed_out,canceled} |

### 创建任务请求
```json
{
  "name": "批量重启 nginx",
  "kind": "script",
  "script_id": 12,
  "script_version": 3,
  "params": { "port": "8080" },
  "target_host_ids": [1, 2, 3],
  "mode": "batch",
  "timeout_sec": 300,
  "retry": 0
}
```
kind=command 时传 `command`（明文命令），kind=script 时传 script_id/script_version+params。
响应 data：
```json
{
  "id": 501, "task_no": "20260812-001",
  "status": "awaiting_approval",
  "approve_required": true,
  "approval_id": 88,
  "sensitive_flag": true
}
```
> 后端行为：命中敏感词或 `target_host_ids.length >= 50`(config_rule) → approve_required=true、status=awaiting_approval 并生成审批单；否则直接投递执行。并发守卫（全局 50/单主机 5，config_rule）超限时任务进入排队，接口返回 200 状态 running/pending，前端以 stats 展示排队。

## 6. WebSocket — 用户实时回显
```
WSS /api/v1/ws/exec/{task_host_id}?token=<短期JWT(5min, 仅该task_host_id)>
```
- 服务端→客户端：
  ```json
  { "type": "log", "data": { "seq": 1, "level": "info", "content": "restarting...", "created_at": "..." } }
  { "type": "status", "data": { "status": "running" } }
  ```
- 客户端→服务端：`{ "type": "stop" }`、`{ "type": "ping" }`。
- 可靠性：断线重连后按 `after_seq` 调 GET /exec/tasks/{id}/hosts/{tid}/logs 补拉；序号去重防乱序。
- 安全：token 为绑定 `task_host_id` 的短期 JWT（5min），仅用于握手鉴权；连接建立后保持至任务结束（长任务不受 5min 限制），断线重连/续期经 `GET /exec/tasks/{id}/hosts/{tid}/ws-token` 重新获取。
- 实现注意：静态段路由（如 `GET /assets/hosts/stats`、`GET /exec/tasks/{id}/stats`）须注册在参数段路由（`{id}`）之前，防止 "stats" 被当 id 解析。

## 6.5 Web 终端（交互式会话，一期）
### REST
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /terminals | 分页：host_id/status/我的 |
| POST | /terminals | {host_id} → {session_id, ws_token, require_approval}（校验主机可见；敏感主机须审批后放行，其余默认放行） |
| GET | /terminals/{id} | 详情（host/状态/时长/录制信息） |
| POST | /terminals/{id}/close | 关闭/强制断开 |
| GET | /terminals/{id}/recording | 回放：?after_offset=&size= 录制偏移续拉；**独立鉴权（仅授权角色）+回放操作写审计**；按保留期限可访问，越权 403/超期 404 |
### WebSocket（交互流）
```
WSS /api/v1/ws/terminal/{session_id}?token=<5minJWT, 绑定session_id>
```
- S→C：`{ "type":"output", "data":{ "data":"\r\n$ ", "offset":123, "ts":"..." } }`（原始流，offset 递增用于续拉/乱序保护）
- S→C：`{ "type":"status", "data":{ "status":"open|closed|idle_timeout|duration_limit" } }`
- C→S：`{ "type":"input", "data":{ "data":"ls -la\r" } }`
- C→S：`{ "type":"resize", "data":{ "cols":120, "rows":40 } }`
- 鉴权：token 绑定 session_id 且会话目标主机在访问者可见主机组内（防 IDOR）；连接保持至会话结束。
- 会话级控制：单用户并发上限/全局上限（超限 429）、空闲自动断开、时长上限（config_rule 可配）；超限/断开返回 status 帧。
- 录制：Agent 会话模式(pty) 输入+输出完整录制，**AES-GCM 加密存储**；回放独立鉴权+写审计；保留期限可配(默认30天)+防导出管控+存储访问白名单。
### 权限点
terminal:list / terminal:create / terminal:close / terminal:view / terminal:replay

## 7. 脚本库
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /scripts | 分页：name/type |
| GET | /scripts/{id} | 详情（含 current_version） |
| POST | /scripts | {name,type,content,params_def,remark} → 建脚本+版本1 |
| PUT | /scripts/{id} | 编辑内容 → 新版本（version+1） |
| DELETE | /scripts/{id} | 删除（被引用 409） |
| GET | /scripts/{id}/versions | 版本列表 |
| GET | /scripts/{id}/versions/{version} | 某版本内容 |
| POST | /scripts/{id}/rollback | {version} 回滚 current_version |
| POST | /scripts/{id}/test | {params} 参数校验试算 |

## 8. 定时任务
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /schedules | 分页 |
| POST | /schedules | {name,kind,script_id/command,params,trigger_type,cron_expr/interval_sec,target_host_ids,timeout_sec,retry,concurrency_limit,enabled} |
| PUT | /schedules/{id} | 编辑（含 timezone） |
| DELETE | /schedules/{id} | 删除 |
| PUT | /schedules/{id}/status | {enabled} |
| POST | /schedules/{id}/run-now | 立即执行一次 |
| GET | /schedules/{id}/runs | 执行历史分页 |
| POST | /schedules/{id}/runs/{run_id}/retry | 重试失败轮次 |

## 9. 审批中心
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /approvals | 分页（待办：requester_id=me or approver role；状态/类型过滤） |
| GET | /approvals/{id} | 详情（含记录时间线） |
| POST | /approvals/{id}/approve | {comment} 通过（乐观锁，并发返回 409） |
| POST | /approvals/{id}/reject | {comment} 拒绝 |
| POST | /approvals/{id}/cancel | 发起人取消 |
| GET | /approvals/rules | 敏感规则列表 |
| POST | /approvals/rules | {name,kind[keyword/count],value,enabled} |
| PUT | /approvals/rules/{id} | 编辑 |
| DELETE | /approvals/rules/{id} | 删除 |

- 幂等：同一 exec_task 只能有一张审批单（biz_id 唯一），重复创建返回 409；approve/reject 用版本乐观锁，并发冲突返回 409 提示刷新。

## 10. 通知中心
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /notify/channels | 列表（config mask） |
| POST | /notify/channels | {name,type,config{...},enabled} |
| PUT | /notify/channels/{id} | 编辑 |
| DELETE | /notify/channels/{id} | 删除 |
| PUT | /notify/channels/{id}/status | 启停 |
| POST | /notify/channels/{id}/test | {title,content} 测试发送 |
| GET | /notify/records | 分页：channel_id/scene/status/时间范围 |
| POST | /notify/records/{id}/resend | 重发失败记录 |

## 11. 仪表盘
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /dashboard/stats | {host_total,host_online,tasks_running,today_tasks,today_success,pending_approvals} |
| GET | /dashboard/task-trend | ?days=7 → [{date,total,success,failed}] |
| GET | /dashboard/recent-tasks | 最近 10 条 |
| GET | /dashboard/recent-approvals | 最近 10 条待办/已办 |

## 12. Agent 接口（WebSocket）
```
WSS /api/v1/agent/ws?agent_id=&token=<X-Agent-Token>
```
### 帧协议（JSON 文本帧）
| 方向 | type | data |
|------|------|------|
| C→S | hello | {agent_id, hostname, ip, os_type, os_version, agent_version} |
| C→S | heartbeat | {ts, metrics:{cpu,mem,disk}}（每 30s） |
| C→S | exec_log | {task_host_id, seq, level, content}（可批量 {items:[]}） |
| C→S | exec_result | {task_host_id, status, exit_code, started_at, finished_at, summary} |
| C→S | pong | {} |
| S→C | hello_ack | {server_time} |
| S→C | heartbeat_ack | {now} |
| S→C | exec | {task_host_id, task_no, kind, script/command, params, timeout_sec} |
| S→C | stop | {task_host_id} |
| S→C | session_open | {session_id, cols, rows}（终端会话模式：pty） |
| S→C | session_input | {session_id, data} |
| S→C | session_stop | {session_id} |
| C→S | session_output | {session_id, data, offset}（pty 输出流，录制+转发） |
| S→C | ping | {} |

- 鉴权失败服务端关闭连接；Agent 断线指数退避重连（1s→30s）；90s 无心跳离线。
- 身份校验：服务端校验 agent_id 与 token 归属一致，禁止伪造 agent_id 冒充；生产强制 TLS（WSS），MVP 亦支持。
- 一期"连通性检测"：服务端向目标 Agent 发 `exec`（`echo __pong__`）或复用心跳 ack 判定。

## 13. 契约实现顺序（后端）
P0（阶段1-2）：auth/*、system/*（含审计查询与导出）、assets/*、/ws/exec/*、agent/ws 协议
P1（阶段3）：exec/*、scripts/*、agent 执行链路
P2（阶段4）：approvals/*、schedules/*、notify/*、terminals/*（REST+WS 会话流）
P3（阶段5）：dashboard/*（audit export 已随 system/* 于阶段1 提供）
