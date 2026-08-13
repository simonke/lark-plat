"""FastAPI application entrypoint: lifespan, middleware, router registration, exception handlers.

Contract: unified Result envelope, append-only audit, WebSocket gateways.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.audit_middleware import AuditMiddleware
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.core.redis_helper import close_redis, get_redis
from app.core.response import CODE_BAD_REQUEST, CODE_SERVER_ERROR, Result
from app.db.session import SessionLocal

# Register all ORM models so Alembic autogenerate can see them.
import app.db.models  # noqa: F401  (import side effects)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    app.state.redis = get_redis()
    yield
    close_redis()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditMiddleware, db_factory=SessionLocal)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=Result.error(exc.code, exc.message, exc.data).model_dump(),
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=Result.error(exc.status_code, str(exc.detail)).model_dump(),
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=Result.error(CODE_BAD_REQUEST, "parameter validation failed", exc.errors()).model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=Result.error(CODE_SERVER_ERROR, "internal server error").model_dump(),
    )


@app.get("/health", tags=["system"], include_in_schema=False)
def health() -> Result:
    return Result.ok({"status": "ok", "env": settings.app_env})


# ---------------------------------------------------------------- routers

from app.api.v1.endpoints import (  # noqa: E402
    approval,
    asset,
    auth,
    dashboard,
    exec,
    notify,
    schedule,
    script,
    system,
)
from app.ws import agent_ws, exec_ws  # noqa: E402

for router in (
    auth.router,
    system.router,
    asset.router,
    script.router,
    exec.router,
    schedule.router,
    approval.router,
    notify.router,
    dashboard.router,
):
    app.include_router(router, prefix=settings.api_prefix)

app.include_router(exec_ws.router, prefix=settings.api_prefix)
app.include_router(agent_ws.router, prefix=settings.api_prefix)
