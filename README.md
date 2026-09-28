<p align="center">
  <img src="docs/assets/logo-banner.svg" alt="lark-plat" width="640"/>
</p>

# lark-plat 自动化运维平台

面向企业 IT 运维团队的统一 Web 运维工作台：把日常分散的登录服务器手工操作，收敛到一套**平台化、可审批、可审计**的工作台；覆盖主机纳管、批量命令/脚本执行、文件分发、定时任务、Web 终端、工单与审批、监控告警、通知中心、编排（Playbook）、CI/CD 集成、知识库，以及 AIOps 智能运维与**受控自动处置（L4）**。

- 统一入口：资产（CMDB）、执行、审批、审计、告警、AI 辅助一体化
- 安全可控：RBAC 权限点 + 全量 append-only 审计 + 审批流程；AI 动作全程留痕、可回滚
- 数据单一真源：单一 PostgreSQL 迁移链（单头）、单一 `DATABASE_URL`
- 实时化：执行日志、告警、工作流运行、Agent 在线状态均经 WebSocket 推送

---

## 功能概览

| 域 | 能力 |
| --- | --- |
| 资产 / CMDB | 主机纳管、凭据、标签、分组；Agent 注册 / 心跳 / 在线状态 |
| 批量执行 | 命令 / 脚本批跑，目标筛选，全局与主机级并发守卫，实时日志（WS），结果回传 |
| 脚本库 / 定时任务 | 脚本版本管理；crontab 托管（Celery/Beat）与执行留痕 |
| 文件分发 | 传输包（package）上传 / 分发 / 校验 |
| Web 终端 | 浏览器内 SSH 会话，会话与操作审计 |
| 工单 / 审批 | 工单状态机（on hold / in progress / resolved / closed）、审批流、评论、RBAC + 审计 |
| 监控告警 | 监控规则、告警事件、聚合与 RCA、告警去重 |
| 通知中心 | 飞书（Lark）等渠道实时通知与模板 |
| 编排（Playbook） | 工作流 DAG 引擎、版本、运行 / 节点运行记录、运行实时 WS |
| CI/CD 集成 | provider / release 集成 |
| 知识库（KB） | 文档摄取 / 分块 / 检索（全文 + 向量存储）、问答沉淀 |
| AIOps 智能运维（P4） | AI 事件台、工单建议 / 采纳、KB 助手、`ai_action` 审计视图 + 证据卡、反馈 |
| 受控自动处置（P6 · L4） | 自动化等级矩阵 L0–L4、白名单、dry-run、熔断、回滚、`auto_policy` 预授权（白名单内低风险自动执行，仍写审计） |

---

## 架构与技术栈

- **后端**：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 + Redis 7 + Celery / Beat
- **前端**：Vue 3 + Vite + TypeScript + Pinia + Element Plus + ECharts
- **Agent**：Go 单二进制，WebSocket 长连（`gorilla/websocket`）
- **部署**：Nginx + Docker Compose（`postgres + redis + backend + celery_worker + celery_beat + web`）
- **数据**：单一 PostgreSQL 库、单一 alembic 迁移链（单头 `P6_REV`）；Redis 作 broker / result / cache

## 目录结构

```
lark-plat/
├── backend/     # FastAPI 后端（app/{core,db,repositories,services,api,schemas,tasks,ws} + alembic + tests + tools）
├── frontend/    # Vue 3 前端工程（Vite / Pinia / Element Plus）
├── agent/       # Go Agent（WS 长连，命令下发执行）
├── deploy/      # docker-compose.yml、nginx.conf、init.sql、.env.example
├── tools/       # 联调 / 测试夹具（如 mock_agent.py）
├── docs/        # 需求 / 架构 / 接口 / 模块 / 验收 / 结项等文档
└── README.md
```

---

## 部署（Docker Compose，推荐）

### 前置条件

- Docker Engine 24+ 与 Docker Compose v2
- 宿主机端口 `8000` 可用（前端与 API 经 Nginx 统一入口）

### 步骤

> ⚠ 前端 `frontend/dist` 是**构建产物、不入库**（见 `frontend/DIST.md`），而 `deploy` 的 `web`（Nginx）**只读挂载**该目录 ⇒ **必须先在启动前构建前端**，否则页面空白。

```bash
# 1) 构建前端静态资源（Node 24 / npm 11）
cd frontend && npm ci && npm run build && cd ..

# 2) 配置环境变量
cp deploy/.env.example  deploy/.env     # Compose 插值读取此文件（POSTGRES_* 必填）
cp backend/.env.example backend/.env    # 应用密钥 / DB / Redis（见“配置项”）

# 编辑 deploy/.env：至少设置强口令 POSTGRES_PASSWORD
# 编辑 backend/.env：至少设置 SECRET_KEY、CREDENTIAL_ENCRYPT_KEY、（生产）SEED_ADMIN_PASSWORD

# 3) 一键启动（首次会构建后端镜像）
cd deploy
docker compose up -d --build
```

启动时自动完成：PostgreSQL 首次初始化（`deploy/init.sql`，append-only 审计函数）→ 后端入口脚本 **`alembic upgrade head`** → 启动 `uvicorn`（默认 2 workers）→ 应用启动时幂等 seed（权限点 / 默认角色 / 引导账号）→ Celery worker / beat。

### 访问地址

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000 | Web 前端（Nginx 静态资源 + `/` SPA 回退） |
| http://localhost:8000/docs | Swagger UI（OpenAPI） |
| http://localhost:8000/openapi.json | OpenAPI 契约 |
| ws://localhost:8000/api/v1/agent/ws | Agent WebSocket 接入 |

> 对宿主机仅暴露 Nginx 的 `8000`；`backend` 的 `8000` 只在 Compose 网络内 `expose`（不映射）。`/`（SPA 回退）、`/docs`、`/openapi.json`、`/api/`、`/api/v1/{ws,agent}/` 均由 `deploy/nginx.conf` 反代至 `backend:8000`（同源，无 CORS 问题）。

### 默认账号（仅 dev / test）

应用启动 seed 预置三个账号，**dev/test 下默认口令 `admin@larkplat`**；`APP_ENV=prod` 时**必须**显式设置 `SEED_ADMIN_PASSWORD`，否则跳过引导账号（fail-safe）。

| 用户名 | 角色 |
| --- | --- |
| `admin` | 管理员（全部权限） |
| `operator` | 运维操作员 |
| `viewer` | 只读观察员 |

> 生产环境请立即修改默认口令，并使用强随机 `SECRET_KEY` 与 `CREDENTIAL_ENCRYPT_KEY`。

### 常用运维命令

```bash
cd deploy
docker compose ps                     # 查看服务状态
docker compose logs -f backend        # 跟踪后端日志
docker compose exec backend alembic upgrade head   # 手动执行迁移
docker compose exec backend alembic heads          # 查看迁移头（应单头 P6_REV）
docker compose up -d --build          # 拉取代码后重建升级
docker compose down                   # 停止（保留数据卷）
docker compose down -v                # 停止并删除数据卷（清空数据，慎用）
```

---

## 启动方法（本地开发，非 Docker）

### 依赖

Python 3.12、Node 24 / npm 11、Go 1.26、PostgreSQL 16、Redis 7。

### 后端

```bash
cd backend
python -m venv .venv
# Windows (PowerShell): .venv\Scripts\pip install -e .
# macOS/Linux:          source .venv/bin/activate && pip install -e .

cp .env.example .env          # 配置 DATABASE_URL / REDIS_URL / SECRET_KEY 等
alembic upgrade head          # 建表 + 迁移到单头 P6_REV
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm ci
npm run dev      # Vite 开发服务器 → http://localhost:5173
npm run build    # 产出 dist/（deploy/docker-compose.yml 只读挂载）
npm run test     # vitest
```

### Agent

```bash
cd agent
go build -o lark-agent .
./lark-agent \
  --server ws://127.0.0.1:8000/api/v1/agent/ws \
  --token  <AGENT_REGISTRATION_TOKEN> \
  --id     <AGENT_ID> \
  --interval 30s
```

> 联调可用 `tools/mock_agent.py` 模拟 Agent（用法见 `tools/README.md`）。

---

## 配置项（关键环境变量）

### `deploy/.env`（Compose 插值）

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `POSTGRES_USER` | 否 | 数据库用户，默认 `lark` |
| `POSTGRES_PASSWORD` | **是** | 数据库口令（未设置 Compose 直接 fail-fast） |
| `POSTGRES_DB` | 否 | 数据库名，默认 `lark_plat` |

### `backend/.env`（应用）

| 变量 | 说明 |
| --- | --- |
| `APP_ENV` / `DEBUG` / `LOG_LEVEL` | 运行环境（`dev`/`prod`）、调试、日志级别 |
| `SECRET_KEY` | JWT（HS256）签名密钥（生产务必更换为长随机串） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token 有效期 |
| `CREDENTIAL_ENCRYPT_KEY` | 敏感凭据 AES-GCM 加密密钥（仅环境注入，不入库/镜像） |
| `DATABASE_URL` | `postgresql+psycopg2://<user>:<pwd>@<host>:5432/<db>` |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis 连接（cache / broker / result） |
| `EXEC_GLOBAL_CONCURRENCY` / `EXEC_HOST_CONCURRENCY` / `EXEC_BATCH_THRESHOLD` | 执行并发守卫与批量阈值 |
| `CORS_ORIGINS` | 允许的前端来源（如 `["http://localhost:5173"]`） |
| `AUDIT_APPEND_ONLY` / `LOGIN_MAX_FAILURES` / `LOGIN_LOCK_MINUTES` | 审计与登录安全策略 |
| `SEED_ADMIN_PASSWORD` | 引导账号口令；`prod` 必填 |

---

## 质量与测试

- **后端**：`pytest`（单元 / 集成 / 契约锁）。契约锁把接口 / 迁移 / 审计等关键不变量固化为静态断言，防止静默回归。
- **迁移治理**：单一迁移链 + 单一头 `P6_REV`；共享库迁移白名单见 `docs/migration-shared-db-allowlist.md`。
- **前端**：`vue-tsc` 类型检查（0 error）+ `vitest`（多文件用例）+ `vite build`。
- **上线就绪闸（live readiness gate）**：`backend/tools/live_readiness_smoke.py` 对目标环境做契约 / 触库 / DB 版本三项校验；验收策略见 `docs/live-acceptance-policy.md`。

---

## 文档

| 文档 | 路径 |
| --- | --- |
| 需求规格（主 PRD v1.0） | `docs/requirements.md` |
| 架构设计 | `docs/architecture.md`、`docs/architecture-phase23.md` |
| 接口契约 | `docs/api-design.md`、`docs/api-design-v3.md`、`docs/openapi.json` |
| 模块设计 | `docs/module-design.md` |
| 任务分配与里程碑 | `docs/task-allocation.md` |
| P4 AIOps 需求 + 产品设计 v1.0 | `docs/p4-requirements-product-design-v1.0.md` |
| P6 受控自动处置 需求 + 产品设计 v0.1 | `docs/p6-requirements-product-design-v0.1.md` |
| 上线验收策略 | `docs/live-acceptance-policy.md` |
| 共享库迁移白名单 | `docs/migration-shared-db-allowlist.md` |
| 验收清单模板 | `docs/acceptance-checklist-template.md` |
| 结项纪要 | `docs/closeout-2026-09-28.md` |
