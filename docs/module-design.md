# lark-plat 自动化运维平台 — 功能模块设计 v2.1

版本: v2.1（对齐需求 v1.1，US-01~12）  |  日期: 2026-08-12  |  作者: 架构师

## 1. 模块总览（MVP）

```
lark-plat 控制台
├── 1 登录认证
├── 2 仪表盘（工作台）
├── 3 资产管理（CMDB）
├── 4 命令执行/批量任务
├── 5 脚本库
├── 6 定时任务
├── 7 审批中心
├── 8 通知中心
├── 9 系统管理（用户/角色/权限/审计）
├── 10 Web 终端（交互式会话 + 会话录制回放）
└── （部署侧）Agent 客户端
```

> 裁决（刘辉授权架构师复核确认）：Web 终端=一期（会话级录制留痕），文件分发=二期。

## 2. 登录认证（US-01）
- 登录、登出、Token 刷新、当前用户、修改密码；会话超时（access 2h）401 自动跳转。
- 登录页预留多登录方式形态（LDAP/OAuth 二期）。

## 3. 仪表盘
- 统计卡片：主机总数/在线、运行中/今日执行任务数、待我审批数、近期失败数。
- 列表：最近 10 条执行任务、最近 10 条待办审批。
- 图表：近 7 日执行趋势（成功/失败）、主机在线率。

## 4. 资产管理（US-04）
- 主机列表：分页 + 多条件筛选（分组/环境/标签/IP/主机名/状态），服务端分页 + 虚拟滚动。
- 主机详情：基本信息、标签、Agent 状态与最后心跳、连接器（agent/ssh）。
- 主机操作：新增/编辑/删除、批量导入（CSV，行级错误返回）、导出、连通性检测（主动探测）。
- 分组管理：树形增删改；标签管理。
- 凭据管理：SSH 连接器凭据录入（密码/私钥，加密存储，仅 mask 展示）。
- 数据权限：按当前用户可见主机组过滤列表与操作。

## 5. 命令执行/批量任务（US-05/06/12）
- 创建任务：选执行方式（命令/脚本）、目标主机（单选/多选/按分组）、参数、超时、重试、模式（单机/批量）。
- 敏感判定提示：命中敏感词或主机数≥阈值 → 提示"需审批"，创建后进入待审批。
- 执行列表：状态过滤、进度、耗时、任务编号；详情页主机维度结果汇总。
- 实时回显：WebSocket 逐行输出（断线重连、序号防乱序、历史补拉）。
- 控制：终止、重试；批量并发上限/限速提示（超过阈值后端拒绝并提示）。
- 二次确认：删除/批量执行等敏感操作前端交互确认。

## 6. 脚本库（US-07）
- 脚本管理：增删改查、类型（shell/powershell/python）。
- 版本管理：保存即新版本、版本列表、版本对比、回滚（current_version 指向旧版本）。
- 参数化：参数定义（名称/类型/默认值/必填），执行时填充。
- 引用检查：被定时任务/执行任务引用的脚本禁止删除。

## 7. 定时任务（US-08）
- 任务管理：增删改查、启用/禁用。
- 触发配置：Cron 表达式 或 固定间隔（秒），语法校验与预览。
- 绑定内容：命令 或 脚本+参数；目标主机。
- 执行历史：每轮 run 状态、结果、失败原因、手动立即执行/重试。
- 重试策略：失败指数退避重试（可配次数）。

## 8. 审批中心（US-06/09）
- 待办审批：列表（发起人/类型/内容摘要/命中敏感点）、审批（通过/拒绝+意见）。
- 我发起的：状态流转（待审批→已通过/已拒绝/已取消）。
- 已办历史：操作记录。
- 规则配置（管理端）：敏感词维护、批量阈值、审批人（角色）。
- 防重复提交：前端交互锁 + 后端幂等（重复提交返回 409 已存在）。

## 9. 通知中心（US-10）
- 渠道管理：飞书机器人（必做）、邮件、企业微信/钉钉/Webhook（可插拔）、测试发送。
- 模板场景：执行完成/失败、定时任务结果、审批待办/结果。
- 发送记录：状态、失败原因、重发。
- 安全：渠道密钥配置加密存储，页面 mask 展示。

## 10. 系统管理（US-02/03/11）
- 用户管理：增删改查、分配角色、启停、重置密码。
- 角色管理：增删改查、分配权限点（树形勾选）、**分配可见主机组**（数据权限）。
- 权限管理：权限点树维护（预置数据）。
- 审计日志：多维检索（用户/模块/操作/时间/IP）、详情查看（含参数）、导出 CSV；命令执行审计含脚本全文与回放入口。

## 11. Web 终端（交互式会话）
- 会话管理：新建会话（选主机）、会话列表（我的/按主机过滤）、关闭/强制断开、在线状态。
- 终端交互：xterm.js 全屏终端，WS 双向流（输入/输出/resize），断线重连+输出 offset 续拉。
- 会话级控制：单用户并发上限、全局上限、空闲自动断开、时长上限（config_rule 可配），超限提示 429。
- 终端访问审批：按主机 sensitivity_level，敏感主机创建会话须审批（复用审批状态机），normal 主机默认放行+全程录制。
- 会话录制安全：输入+输出 AES-GCM 加密落盘；回放独立鉴权（仅授权角色）+回放写审计；保留期限可配（默认 30 天）+防导出管控+存储访问白名单。
- 审计：会话创建/关闭记 sys_audit_log；录制回放入口关联审计。
- 权限：主机组数据权限一致；WS token 绑定 session_id（防 IDOR）。
- 路由/权限点：/terminals → terminal:list/create/close/view/replay。

## 12. Agent（部署侧，Go）
- WS 长连 + 30s 心跳、命令执行（shell/powershell/python，超时 kill）、日志流回传（seq）、结果上报、stop 响应、指数退避重连、连通性探测响应。
- 配置：`agent.yaml`（server、agent_key、间隔、工作目录、执行账户）。

## 13. 路由-权限映射（前端）
| 路由 | 页面 | 权限点 |
|------|------|--------|
| /login | 登录 | - |
| /dashboard | 仪表盘 | dashboard:view |
| /assets/hosts | 主机 | asset:host:list/add/edit/del/import/export/conn |
| /assets/groups | 分组 | asset:group:list/add/edit/del |
| /assets/credentials | 凭据 | asset:cred:list/add/edit |
| /exec/tasks | 命令执行 | exec:task:list/run/stop/retry/log |
| /scripts | 脚本库 | script:list/add/edit/del/version/rollback |
| /schedules | 定时任务 | schedule:list/add/edit/del/run/retry |
| /approvals | 审批中心 | approval:list/approve/request |
| /terminals | Web 终端 | terminal:list/create/close/view/replay |
| /notify/channels | 通知渠道 | notify:channel:list/add/edit/del/test |
| /notify/records | 发送记录 | notify:record:list |
| /system/users | 用户 | system:user:list/add/edit/del/role |
| /system/roles | 角色 | system:role:list/add/edit/del/perm/group |
| /system/permissions | 权限 | system:permission:list |
| /system/audit-logs | 审计 | system:audit:list/export |

## 14. 前端工程要点
- 结构：`src/{api,components,views,router,stores,types,utils}`；TS 类型由 OpenAPI 生成（`src/types/api`）。
- Axios 统一封装：Token 注入、401 刷新重试、错误提示、Loading、防抖。
- WebSocket 统一封装（`useRealtimeLog`）：重连、seq 防乱序、历史补拉、自动销毁；终端模式复用同一 WS 客户端 + xterm.js。
- 通用组件：TablePage（分页+筛选）、HostSelect（主机选择器，含分组树）、ScriptEditor、StatusTag（状态枚举/颜色常量）、ApprovalTimeline、v-perm 指令。
- 状态/枚举常量：exec/schedule/approval/agent 状态与后端一致（contract.md 兜底）。

## 15. 后端工程要点
- 分层：api(router) → service → repository；schemas(Pydantic) 做入参/出参。
- 统一返回 `Result{code,message,data}`；分页 `PageVO{list,total,page,size}`；全局异常（校验/业务/未知分层）。
- 鉴权：依赖注入 `get_current_user` + 权限依赖；数据权限统一 service 内按可见分组过滤。
- 审计：写操作自动拦截记录（`AuditMiddleware`）；命令执行在 service 显式记录含全文。
- Celery：`exec_dispatch`、`notify_send`、Beat 任务；并发守卫与限速在任务层。
- 测试：pytest + AsyncClient；配置可覆盖（测试库/Redis 独立前缀）。
