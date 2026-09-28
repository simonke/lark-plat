# 部署、启动与运维手册

本文档面向部署与运维 lark-plat 单机环境，覆盖 Docker Compose 部署、本地开发启动、配置、升级迁移与常见问题。范围口径与接口见 `docs/architecture.md`、`docs/architecture-phase23.md`；产品与快速开始见仓库根 `README.md`。

## 1. 部署拓扑

```
Internet/内网 ──► Nginx(web:80 → 宿主机:8000)
                    ├── /            → frontend/dist（静态，SPA fallback）
                    ├── /api/         → backend:8000
                    ├── /api/v1/ws/   → backend:8000（WebSocket 升级）
                    ├── /api/v1/agent/→ backend:8000（WebSocket 升级）
                    ├── /docs         → backend:8000
                    └── /openapi.json → backend:8000
backend(FastAPI) ──► PostgreSQL:5432
                  └─► Redis:6379
celery_worker    ──► Redis(broker) ──► PostgreSQL
celery_beat      ──► Redis(broker)（定时调度）
被管主机 Agent    ──► WSS backend /api/v1/agent/*
```

- Compose 服务：`postgres`、`redis`、`backend`(uvicorn)、`celery_worker`、`celery_beat`、`web`(nginx)。
- 对外仅暴露宿主机 `8000`（nginx）；`backend` 仅在 compose 网络内 `expose 8000`（**勿直连 backend 端口**）。
- 启动顺序由 `depends_on` 健康检查保证：postgres/redis healthy 后 backend 启动。

## 2. 前置条件

- Docker Engine + Docker Compose v2。
- Node.js **20+**（CI 固定 20；本机 24 / npm 11），用于构建前端静态产物 `frontend/dist`。
- 可写磁盘用于数据卷 `pgdata` / `redisdata`。

## 3. 首次部署（Docker Compose）

```bash
# 1) 应用配置：应用密钥与依赖地址
cp backend/.env.example backend/.env
#   必填/建议：SECRET_KEY、CREDENTIAL_ENCRYPT_KEY、SEED_ADMIN_PASSWORD
#   依赖地址在 compose 下由 compose 注入（见下），无需改为容器名

# 2) Compose 变量：数据库账号密码
cp deploy/.env.example deploy/.env
#   设置 POSTGRES_PASSWORD（必填，未设置 compose 直接 fail-fast），可改 POSTGRES_USER / POSTGRES_DB

# 3) 构建前端静态产物（nginx 只读挂载 frontend/dist；缺失则页面空白/404）
cd frontend
npm ci
npm run build
cd ..

# 4) 启动
cd deploy
docker compose up -d --build
```

访问与验证：

```bash
# 打开平台
#   http://localhost:8000
# 后端 API 文档
#   http://localhost:8000/docs
# 健康/契约
curl http://localhost:8000/openapi.json -o /dev/null -w "%{http_code}\n"
```

说明：

- `backend` 容器入口为 `backend/docker-entrypoint.sh`，先执行 `alembic upgrade head`，再 `uvicorn app.main:app`（单一权威启动定义；worker 数由 `UVICORN_WORKERS` 控制，默认 2）。
- 应用启动（lifespan）会幂等 seed（权限点 / 默认角色 / 引导账号）。
- compose 会将 `DATABASE_URL` / `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` 指向容器服务名（`postgres:5432`、`redis:6379`），覆盖 `backend/.env` 中的本地地址。
- `deploy/init.sql` 仅在首次初始化数据卷时执行，创建只追加审计函数；阻断触发器与 `REVOKE` 由 alembic 迁移在表就绪后建立。

## 4. 环境变量

`backend/.env`（应用）关键项：

| 变量 | 说明 |
|------|------|
| `SECRET_KEY` | JWT 签名密钥（HS256） |
| `CREDENTIAL_ENCRYPT_KEY` | 主机凭据 AES-GCM 加密密钥（仅环境注入，不入库/镜像） |
| `DATABASE_URL` | 本地开发时的 PG 连接串；compose 下被覆盖 |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Redis 与 Celery |
| `CORS_ORIGINS` | 允许的前端源，默认 `["http://localhost:5173"]` |
| `SEED_ADMIN_PASSWORD` | 初始管理员口令（生产必填；未设时 dev/test 回落默认） |

`deploy/.env`（compose 插值）：`POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`。

> 安全：`.env` 一律不入库、不入镜像；密钥通过环境变量注入。

## 5. 启动 / 停止 / 日志

```bash
cd deploy
docker compose up -d --build      # 启动（重建镜像）
docker compose ps                 # 状态
docker compose logs -f backend    # 跟踪后端日志
docker compose logs -f celery_worker
docker compose down               # 停止并移除容器（保留数据卷）
docker compose down -v            # 停止并删除数据卷（清库，慎用）
```

单独重启后端（例如改配置后）：

```bash
cd deploy && docker compose up -d --build backend
```

## 6. 数据与备份

- 数据卷：`pgdata`（PostgreSQL 数据）、`redisdata`（Redis AOF）。
- 备份数据库示例（默认在 `deploy/` 目录执行；若从仓库根执行，请加 `-f deploy/docker-compose.yml`）：

```bash
docker compose exec postgres pg_dump -U lark lark_plat > backup_$(date +%F).sql
```

- 恢复前建议先停止写入（停 `backend`/`celery_*`），恢复后再启动。

## 7. 升级与数据库迁移

1. 拉取最新代码（`master`）。
2. 备份数据库（见上）。
3. 重新构建并滚动启动：

```bash
cd frontend && npm ci && npm run build && cd ..
cd deploy && docker compose up -d --build
```

`backend` 启动入口会自动执行 `alembic upgrade head`（单头迁移链）。

迁移治理纪律（生产变更前必读）：

- 迁移**只增不改**：不得改写或删除已发布迁移。
- 迁移链保持**单头**（`alembic heads` 应仅返回一个）。
- 共享/生产库的迁移白名单与解禁流程见 `docs/migration-shared-db-allowlist.md`；涉及 DDL 的变更须经评审授权后再执行。

手动执行迁移（排障时）：

```bash
cd deploy && docker compose exec backend alembic upgrade head
cd deploy && docker compose exec backend alembic current
```

## 8. 本地开发启动（不经 Docker）

前置：本机 PostgreSQL 16、Redis 7；或仅用 `deploy/docker-compose.yml` 起 `postgres redis` 作为依赖。

> ⚠ `postgres` 服务受 `POSTGRES_PASSWORD:?` **fail-fast** 约束 ⇒ 即使只起依赖，也须**先**准备 `deploy/.env`：
>
> ```bash
> cp deploy/.env.example deploy/.env     # 设置 POSTGRES_PASSWORD
> docker compose -f deploy/docker-compose.yml up -d postgres redis   # 可选：仅起依赖
> ```

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate         # Windows；POSIX: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env           # DATABASE_URL/REDIS_URL 指向本机
alembic upgrade head
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm ci
npm run dev                    # http://localhost:5173，已含默认 CORS
```

## 9. 测试与质量门

```bash
# 后端离线门（默认不收集 live 集成夹具）
cd backend && pytest
# 后端 live/seed 集成夹具（显式）
cd backend && pytest tests/integration/stage1
# 前端
cd frontend && npm run type-check && npm run test && npm run build
```

CI 见 `.github/workflows/ci.yml`。

## 10. 常见问题

| 现象 | 原因 / 处理 |
|------|------|
| `docker compose up` 报 `POSTGRES_PASSWORD is required` | 未设置 `deploy/.env` 的 `POSTGRES_PASSWORD`；补齐后重试 |
| 打开 `:8000` 页面为空 / 404 | 未构建 `frontend/dist`；执行 `cd frontend && npm ci && npm run build` 后重启 `web` |
| 后端启动即退出，日志含迁移错误 | 检查 `alembic current` / `alembic heads` 是否单头；数据库连通性 |
| 前端请求 401/跨域 | 确认 `CORS_ORIGINS` 含前端源；本地开发默认 `http://localhost:5173` |
| 端口 `8000` 被占用 | 修改 `deploy/docker-compose.yml` 中 `web` 的 `ports` 映射或释放端口 |
| Agent 不上线 | 检查 Agent 能否访问 `/api/v1/agent/*`（WSS/WS 升级）；心跳应 ≤30s |

## 11. 验收与证据纪律

- Live 验收与证据面纪律：`docs/live-acceptance-policy.md`。
- 批次验收清单模板：`docs/acceptance-checklist-template.md`。
- 结项状态：`docs/closeout-2026-09-28.md`。
