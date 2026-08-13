# lark-plat 自动化运维平台 — 架构设计 v2.1

版本: v2.1（对齐需求 v1.1 + 团队共识）  |  日期: 2026-08-12  |  作者: 架构师

> v2.1 变更：后端技术栈定为 Python FastAPI（团队共识）；新增审批流程模块、定时任务模块；监控告警调整至二期；执行实时回显改 WebSocket；主机连接优先 Agent(WebSocket)，SSH 直连降级；Web 终端入一期（会话级录制留痕），文件分发二期。本版为最终契约基线。

## 1. 项目定位与范围（对齐需求 v1.0）

面向企业 IT 运维团队的统一 Web 运维工作台：将分散的手工服务器操作平台化、可审批、可审计，并通过飞书等渠道实时通知。

- 目标用户：运维工程师 / 运维负责人(值班) / 研发工程师 / 平台管理员
- 规模：≤1000 台主机（列表服务端分页 + 虚拟滚动）

### MVP（一期）
1. 认证与 RBAC（用户/角色/权限点，数据级权限到**主机组**）
2. 主机（资产）管理（录入/分组/标签/连通性状态）
3. 命令执行/批量任务（WebSocket 实时回显、超时中断、并发受控）
4. 脚本库（版本管理、参数化、可复用）
5. 定时任务（Cron/间隔、失败重试、执行历史）
6. 审批流程（高风险操作 发起→审批→执行，幂等防重复）
7. 通知中心（飞书必做，邮件/企业微信/钉钉/Webhook 可插拔）
8. 审计日志（全量留痕、不可篡改、命令回放）
9. Web 终端（交互式会话；**会话级录制留痕**，审计提供会话回放——交互式输入无法逐命令全文留痕，与"逐命令回放"的差异已在需求口径备案）

### 二期
文件分发、监控告警、LDAP/OAuth
### 三期
工单、知识库、CI/CD 集成、编排

## 2. 总体架构（分层）

```
┌────────────────────────────────────────────────────────────┐
│  展示层   Vue3 + Vite + TS + Pinia + Element Plus + ECharts │
│           TS 类型/API 层 由 OpenAPI 自动生成                 │
└──────────────────────────┬─────────────────────────────────┘
                           │ HTTPS / REST + WSS
┌──────────────────────────▼─────────────────────────────────┐
│  接入层   Nginx（静态资源 + 反代 /api + WS 升级）            │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│  应用层   Python 3.12 + FastAPI（模块化单体，单进程/多worker）│
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │ auth     │ asset    │ exec     │ script   │ schedule │  │
│  │ 认证/RBAC│ CMDB     │ 命令执行  │ 脚本库   │ 定时任务 │  │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┤  │
│  │ approval │ notify   │ audit    │ ws       │ agent    │  │
│  │ 审批流程 │ 通知中心 │ 审计     │ WS网关   │ Agent网关│  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│  + Celery(Redis broker)：执行分发/定时beat/通知/限速并发     │
├────────────────────────────────────────────────────────────┤
│  数据层   PostgreSQL 16(JSONB)  |  Redis 7  |  本地磁盘     │
└────────────────────────────────────────────────────────────┘
        ▲ Agent(WebSocket 30s心跳)  |  SSH 直连（降级，凭据加密）
┌────────────────────────────────────────────────────────────┐
│  被管主机 Agent（Go 单二进制，WS 长连，执行+回传+采集）      │
└────────────────────────────────────────────────────────────┘
```

架构决策：
1. **模块化单体**：FastAPI 单应用，按模块目录划分，保留拆服务边界。单后端工程师可维护，避免微服务过度设计。
2. **执行引擎抽象**：`Executor` 接口 → `AgentExecutor`（WS）/ `SshExecutor`（降级）。MVP 以 Agent 为主，SSH 凭据集中加密托管、禁止明文。
3. **审批-执行联动不可绕过**：执行任务创建即进入状态机，敏感操作（命中敏感词/目标主机数≥阈值）必须先过审批，命令执行入口强制校验审批状态。
4. **异步与并发受控**：Celery（Redis broker）承担执行分发/定时/通知；全局并发上限 + 每主机并发上限 + 限速在任务队列层强制。
5. **WebSocket 双通道**：用户侧 `/ws/exec/*` 实时回显（断线重连+序号防乱序）；Agent 侧 `/agent/ws` 心跳+命令下发。
6. **接口契约化**：FastAPI 原生 OpenAPI（/docs、/openapi.json），前端自动生成 TS 类型，前后端字段强一致。

## 3. 技术选型（定稿）

| 层次 | 技术 | 版本 | 说明 |
|------|------|------|------|
| 后端 | Python + FastAPI | 3.12 / ^0.110 | 异步，原生 OpenAPI/WebSocket |
| ORM/迁移 | SQLAlchemy 2.0 + Alembic | ^2.0 | Repository 抽象（DAO 可 mock） |
| 数据库 | PostgreSQL | 16 | JSONB（参数/标签/配置） |
| 缓存/限流 | Redis | 7.x | token 黑名单、refresh、限速、分布式锁 |
| 异步任务 | Celery + Beat | ^5.3 | 执行分发/定时/通知，rate_limit+并发守卫 |
| 认证 | JWT（python-jose）+ RBAC | | HS256，BCrypt(passlib) 密码 |
| 校验 | Pydantic v2 | ^2 | 入参校验，字段枚举/长度/范围 |
| Agent | Go | 1.22+ | WS 长连，编译单二进制 |
| 前端 | Vue3 + Vite + TS | ^3.4 / ^5 | Element Plus + Pinia + ECharts |
| 部署 | Docker Compose | | postgres+redis+celery_worker+celery_beat+backend+web |

## 4. 部署架构

```
Internet ──► Nginx(:80/443)
               ├── /          → frontend/dist（静态）
               ├── /api/**    → backend:8000
               └── /ws/**     → backend:8000（WS 升级）
backend(FastAPI) ──► PostgreSQL:5432
                  ──► Redis:6379
celery_worker ──► Redis(broker) ──► PostgreSQL
celery_beat  ──► Redis(broker)（定时调度）
被管主机 Agent ──► WSS backend/agent/ws（内网）
```

- Docker Compose 服务：postgres、redis、backend(uvicorn)、celery_worker、celery_beat、web(nginx)。
- 环境变量化配置（.env 不入库），密钥经 `SECRET_KEY`/`CREDENTIAL_ENCRYPT_KEY` 注入。

## 5. 代码仓库结构

```
lark-plat/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 入口（lifespan、路由注册、CORS）
│   │   ├── core/                 # config、security(JWT/密码/凭据加密)、exceptions、logging、audit 中间件
│   │   ├── db/                   # engine、session、base、models 目录
│   │   ├── repositories/         # Repository 抽象（DAO，可 mock）
│   │   ├── services/             # 业务逻辑（可单测）
│   │   ├── api/v1/               # routers：auth/users/roles/hosts/scripts/exec/schedule/approval/notify/audit/dashboard
│   │   ├── schemas/              # Pydantic DTO
│   │   ├── tasks/                # Celery：exec_dispatch/notify/beat_schedule
│   │   └── ws/                   # exec WS manager + agent WS manager
│   ├── alembic/                  # 迁移脚本
│   ├── tests/                    # pytest（unit + api 集成）
│   ├── pyproject.toml / .env.example
│   └── Dockerfile
├── frontend/                     # Vue3 工程（src/{api,components,views,router,stores,types,utils}）
├── agent/                        # Go Agent（WS 客户端 + 执行器）
├── deploy/                       # docker-compose.yml、nginx.conf、init.sql
├── docs/                         # 设计文档
└── README.md
```

## 6. 非功能设计

- **性能**：≥500 并发请求；列表服务端分页；WS 日志增量 seq 游标防乱序。
- **并发受控**（US-12）：全局执行并发上限（默认 50）、单主机并发上限（默认 5）、批量任务限速（Celery rate_limit + Redis 令牌桶），队列层强制、防超发。
- **可用性**：Agent WS 断线指数退避重连；90s 无心跳判定离线；执行超时双保险（Agent 本地计时 + 后端扫描）。定时任务执行幂等，失败按策略重试。
- **安全**：密码 BCrypt、JWT 黑名单、逐接口鉴权+RABC、主机组数据权限、敏感命令白名单/敏感词审批、命令审计全留痕、凭据 AES-GCM 加密存储、日志脱敏、登录限流。
- **审计**：append-only（应用层禁止 UPDATE/DELETE），含操作人/IP/对象/参数/结果；命令执行记录含脚本全文与执行日志（回放）；可选哈希链防篡改。
- **可观测**：结构化日志 + trace_id（关联 task_no/approval_no），Celery 任务日志分级。

## 7. 风险与对策

| 风险 | 对策 |
|------|------|
| Agent 跨平台差异 | 执行器抽象；脚本 type=shell/powershell/python 选择解释器；MVP 以 Linux 为主 |
| 审批绕过风险 | 命令执行入口强制校验审批状态；审批幂等+乐观锁；审计留痕 |
| 批量并发失控 | 队列层全局/单主机并发守卫 + 限速，拒绝超发 |
| WS 断线丢日志 | 日志写 DB（seq 游标）双通道：WS 实时 + 历史拉取兜底 |
| 凭据泄露 | 集中加密存储、最小权限账号、日志禁止输出 |
