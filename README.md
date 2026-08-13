# lark-plat 自动化运维平台

面向企业 IT 运维团队的统一 Web 运维工作台：主机纳管、批量命令/脚本执行、定时任务、审批流程、通知中心与全量审计，支持飞书（Lark）等渠道实时通知。

## 技术栈

- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL 16 + Redis 7 + Celery/Beat
- 前端：Vue 3 + Vite + TypeScript + Pinia + Element Plus + ECharts
- Agent：Go 单二进制（WebSocket 长连）
- 部署：Docker Compose（postgres + redis + backend + celery_worker + celery_beat + web）

## 目录结构

```
lark-plat/
├── backend/     # FastAPI 后端（app/core/db/repositories/services/api/schemas/tasks/ws + alembic + tests）
├── frontend/    # Vue3 前端工程
├── agent/       # Go Agent
├── deploy/      # docker-compose.yml、nginx.conf、init.sql
├── docs/        # 设计文档
└── README.md
```

## 快速开始

```bash
cd deploy && docker compose up -d --build
```

后端 API 文档：http://localhost:8000/docs（OpenAPI：/openapi.json）

## 文档

- 架构设计：`docs/architecture.md`
- 系统设计：`docs/system-design.md`
- 接口契约：`docs/api-design.md`
- 模块设计：`docs/module-design.md`
- 任务分配：`docs/task-allocation.md`
