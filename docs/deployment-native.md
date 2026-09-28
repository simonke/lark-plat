# 原生（非 Docker）生产部署手册

本文档面向**不经容器**在单机/主机上以生产方式部署 lark-plat：Nginx + `uvicorn` + Celery worker/beat + 原生 PostgreSQL/Redis，进程由 systemd 托管。

- Docker Compose 部署（推荐、已验证路径）见 `docs/deployment.md`。
- 本文为**原生生产**补充路径；它同样适用于已有 Nginx/PG/Redis 的存量主机。

> **验证状态（诚实标注）**：本环境无 Docker、且未在本机跑通完整原生生产链路；本文按 `deploy/` 与源码静态核对编写，其中的端口/路径/进程口径与 compose 一致。首次上生产请按第 13 节逐项自检。

## 1. 拓扑

```
Internet/内网 ──► Nginx(宿主机:443/80, TLS)
                    ├── /             → /var/www/lark-plat/dist（静态，SPA fallback）
                    ├── /api/         → 127.0.0.1:8000
                    ├── /api/v1/ws/   → 127.0.0.1:8000（WebSocket 升级）
                    ├── /api/v1/agent/→ 127.0.0.1:8000（WebSocket 升级）
                    ├── /docs         → 127.0.0.1:8000
                    └── /openapi.json → 127.0.0.1:8000
uvicorn(FastAPI, :8000) ──► PostgreSQL 127.0.0.1:5432
                        └──► Redis 127.0.0.1:6379
celery_worker           ──► Redis(broker) ──► PostgreSQL
celery_beat             ──► Redis(broker)（定时调度）
被管主机 Agent(Go)       ──► WSS Nginx /api/v1/agent/*
```

与 compose 一致的**对外仅暴露 Nginx**；后端 `:8000` 只监听 `127.0.0.1`（**勿直连**）。

## 2. 前置条件

| 组件 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 后端 |
| Node.js | 20+（CI 固定 20） | 构建前端 `dist` |
| Go | 1.26 | 构建 Agent 二进制（可选，按需分发） |
| PostgreSQL | 16 | 数据库 |
| Redis | 7 | broker/result/cache |
| Nginx | 1.24+ | 反向代理 + 静态 |

系统服务建议以专用用户运行（示例 `larkplat`），目录约定：

- 代码：`/opt/lark-plat`
- 运行数据：`/var/lib/lark-plat/`（含 `transfer/packages`）
- 日志：`/var/log/lark-plat/`（或走 journald）

## 3. 数据库初始化（原生）

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE lark LOGIN PASSWORD '强随机口令';
CREATE DATABASE lark_plat OWNER lark;
SQL

# 关键：先建 append-only 审计函数（compose 由 init.sql 在首启时执行）
psql "postgresql://lark:强随机口令@127.0.0.1:5432/lark_plat" -f /opt/lark-plat/deploy/init.sql
```

- `init.sql` 只建函数；**阻断触发器与 `REVOKE` 由 alembic 迁移在表就绪后建立**，无需手工执行建表 SQL。
- 数据库口令/地址写入 `backend/.env` 的 `DATABASE_URL`（原生下**不要**依赖 compose 注入）。

## 4. 后端安装与配置

```bash
cd /opt/lark-plat/backend
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"        # 或 pip install .（生产可省 dev 依赖）

cp .env.example .env           # 编辑下列关键项
```

`backend/.env` 生产关键项：

| 变量 | 说明 |
|------|------|
| `APP_ENV` | 置 `prod` |
| `SECRET_KEY` | JWT(HS256) 强随机（务必更换） |
| `CREDENTIAL_ENCRYPT_KEY` | 主机凭据 AES-GCM 密钥（仅环境注入，不入库/镜像） |
| `SEED_ADMIN_PASSWORD` | 引导管理员口令；`APP_ENV=prod` 必填，否则跳过引导账号 |
| `DATABASE_URL` | `postgresql+psycopg2://lark:<口令>@127.0.0.1:5432/lark_plat` |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://127.0.0.1:6379/{0,1,2}` |
| `CORS_ORIGINS` | 同源反代下可保持默认 |
| `transfer_store_dir` | **必须为绝对路径**（如 `/var/lib/lark-plat/transfer/packages`） |

> ⚠ `transfer_store_dir` 默认是相对路径（`data/transfer/packages`），在 systemd 下会相对单位工作目录解析；原生部署请显式改**绝对路径**并纳入备份（见第 11 节）。

迁移：

```bash
alembic upgrade head          # 建表 + 迁移到单头（当前 P6_REV）
alembic heads                 # 应仅一个头
```

## 5. 前端构建

```bash
cd /opt/lark-plat/frontend
npm ci
npm run build                 # 产出 dist/（入库与否见 frontend/DIST.md；dist 不入库）
sudo mkdir -p /var/www/lark-plat
sudo cp -r dist /var/www/lark-plat/
```

`vite build` 前会执行 `vue-tsc -b` 类型检查；构建必须成功产出 `dist/`，否则 Nginx 页面空白。

## 6. Nginx 反向代理（原生配置）

**核心差异**：`deploy/nginx.conf` 面向容器（`proxy_pass` 指向服务名 `backend:8000`、静态根为容器路径），且被 `docker-compose.yml` 挂为 web 容器配置 ⇒ **原生部署不要改它**（改了会破 Docker 模式）。原生改用仓库内另备的 **`deploy/nginx.native.conf`**（`proxy_pass`→`127.0.0.1:8000`、`root`→宿主机 dist；共 5 处反代）。复制到 `/etc/nginx/conf.d/larkplat.conf`，替换域名与证书路径即可。下文为其内容：

```nginx
server {
    listen 443 ssl http2;
    server_name lark.example.com;

    ssl_certificate     /etc/nginx/ssl/lark.crt;
    ssl_certificate_key /etc/nginx/ssl/lark.key;

    client_max_body_size 20m;          # 与 deploy/nginx.conf 保持一致

    # WebSocket
    location /api/v1/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
    }
    location /api/v1/agent/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 3600s;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
    location / {
        root /var/www/lark-plat/dist;  # 宿主机绝对路径（替换容器 /usr/share/nginx/html）
        index index.html;
        try_files $uri $uri/ /index.html;   # 保留 SPA fallback
    }
}
```

> - **WSS 必须经 TLS**：Agent 走 `wss://`，因此生产须 `listen 443 ssl`（`deploy/nginx.conf` 仅 `listen 80`，仅供容器内网）。
> - 切勿漏改任一 `proxy_pass`，否则对应路由 502。

## 7. 进程托管（systemd）

`backend/.env` 由 `EnvironmentFile` 注入；`WorkingDirectory` 影响相对路径，故 `transfer_store_dir` 已建议用绝对路径。

`/etc/systemd/system/lark-backend.service`：

```ini
[Unit]
Description=lark-plat backend (uvicorn)
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=simple
User=larkplat
WorkingDirectory=/opt/lark-plat/backend
EnvironmentFile=/opt/lark-plat/backend/.env
ExecStart=/opt/lark-plat/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/lark-celery-worker.service`：

```ini
[Unit]
Description=lark-plat celery worker
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=larkplat
WorkingDirectory=/opt/lark-plat/backend
EnvironmentFile=/opt/lark-plat/backend/.env
ExecStart=/opt/lark-plat/backend/.venv/bin/celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/lark-celery-beat.service`：

```ini
[Unit]
Description=lark-plat celery beat
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=larkplat
WorkingDirectory=/opt/lark-plat/backend
EnvironmentFile=/opt/lark-plat/backend/.env
ExecStart=/opt/lark-plat/backend/.venv/bin/celery -A app.tasks.celery_app.celery_app beat --loglevel=INFO
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lark-backend lark-celery-worker lark-celery-beat
```

- **生产禁用 `--reload`**；单实例、`--workers N`（默认 2，与架构 §2/§4 口径一致）。
- 应用启动（lifespan）会幂等 seed（权限点/默认角色/引导账号）。

## 8. Agent 部署（可选）

```bash
cd /opt/lark-plat/agent
go build -o /usr/local/bin/lark-agent .
# 在被管主机运行（登记 token 由平台签发）
lark-agent --server wss://lark.example.com/api/v1/agent/ws \
           --token <AGENT_REGISTRATION_TOKEN> --id <AGENT_ID> --interval 30s
```

> 已知限制：当前 Agent 心跳循环存在阻塞读，实测心跳可能显著大于 `interval`（见台账 B3，登记为待修）；不影响连通性判定。

## 9. 启动 / 停止 / 日志 / 健康

```bash
sudo systemctl status lark-backend
sudo journalctl -u lark-backend -f
sudo journalctl -u lark-celery-worker -f

# 健康/契约
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/openapi.json     # 期望 200
cd /opt/lark-plat/backend && . .venv/bin/activate && alembic current            # 期望单头
```

## 10. 升级与迁移

```bash
cd /opt/lark-plat && git pull
# 备份（见第 11 节）
cd backend && . .venv/bin/activate && pip install -e ".[dev]" && alembic upgrade head
cd ../frontend && npm ci && npm run build && sudo cp -r dist /var/www/lark-plat/
sudo systemctl restart lark-backend lark-celery-worker lark-celery-beat
```

迁移纪律（同 `docs/deployment.md`）：**只增不改**、保持**单头**、共享/生产库 DDL 走 `docs/migration-shared-db-allowlist.md` 评审授权。

## 11. 数据与备份

- PostgreSQL：`pg_dump -U lark lark_plat > backup_$(date +%F).sql`（恢复前建议先停写：停 `lark-backend`/`lark-celery-*`）。
- 传输包：备份 `transfer_store_dir`（默认 `data/transfer/packages`，生产已改绝对路径）。
- Redis：作 broker/result/cache，一般无需持久备份；持久化按需开 AOF。

## 12. Redis 与降级

- Redis 7 为 Celery（broker/result）与实时缓存依赖，原生生产**应安装并常驻**。
- 若 Redis 不可达：缓存/实时相关能力**优雅降级**（不阻塞进程启动），但**异步任务（定时/摄取等）不可用** ⇒ 生产须保证 Redis 可用。

## 13. 常见问题

| 现象 | 原因 / 处理 |
|------|------|
| 全部路由 502 | 任一 `proxy_pass` 仍是 `backend:8000`（容器名）；改为 `127.0.0.1:8000` |
| 页面空白/404 | 未构建或未部署 `dist`；确认 `root` 指向宿主机绝对路径且 `try_files` 存在 |
| 启动即退出，日志含迁移错误 | 检查 PG 连通性、`alembic heads` 是否单头、`init.sql` 审计函数是否已建 |
| 前端请求 401/跨域 | 确认 `CORS_ORIGINS`；同源反代下通常无 CORS 问题 |
| Agent 不上线 | 确认 Nginx WS 路由 `/api/v1/agent/` 已改 `127.0.0.1` 且经 WSS(TLS)；心跳见 §8 限制 |
| 传输/附件丢失 | `transfer_store_dir` 为相对路径、随重启/工作目录漂移；改绝对路径（§4） |

## 14. 与 Docker Compose 部署的差异

| 项 | Docker Compose（`docs/deployment.md`） | 原生（本文） |
|----|----------------------------------------|--------------|
| 后端地址 | 服务名 `backend:8000` | `127.0.0.1:8000` |
| 静态根 | 容器 `/usr/share/nginx/html` | 宿主机 `/var/www/lark-plat/dist` |
| 依赖注入 | compose `environment:` 覆盖 | `backend/.env`（`EnvironmentFile`） |
| 迁移 | 入口脚本自动 `alembic upgrade head` | 手工 `alembic upgrade head` |
| 进程托管 | compose `restart: unless-stopped` | systemd 单元 |
| DB 引导函数 | `init.sql` 首启自动 | 手工 `psql -f deploy/init.sql`（迁移前） |
| TLS/WSS | 需另置前置反代 | Nginx 直接 `listen 443 ssl` |

## 15. 参考

- Docker 部署与本地开发：`docs/deployment.md`
- 上线验收与证据纪律：`docs/live-acceptance-policy.md`
- 迁移白名单：`docs/migration-shared-db-allowlist.md`
- 架构：`docs/architecture.md`、`docs/architecture-phase23.md`
