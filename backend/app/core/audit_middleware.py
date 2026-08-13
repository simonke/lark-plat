"""Audit middleware: append-only logging of write operations (US-11).

Only INSERT is performed at application level. The DB layer revokes UPDATE/DELETE
permissions on sys_audit_log and adds a trigger rejecting mutations (double safety,
see deploy/init.sql). Sensitive fields (password, secret, token) are redacted.
"""

from __future__ import annotations

import json
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_var, trace_id_var

SENSITIVE_KEYS = {"password", "secret", "old_password", "new_password", "key", "passphrase",
                  "refresh_token", "access_token", "secret_enc", "key_enc", "config_enc"}

AUDIT_EXCLUDED_PREFIXES = ("/docs", "/openapi.json", "/ws/exec", "/agent/ws")


def _redact(data: dict | None) -> dict | None:
    if not data:
        return data
    out: dict = {}
    for k, v in data.items():
        if k in SENSITIVE_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        elif isinstance(v, list):
            out[k] = [_redact(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db_factory):
        super().__init__(app)
        self.db_factory = db_factory

    async def dispatch(self, request: Request, call_next):
        trace_id = trace_id_var.get() or uuid.uuid4().hex[:16]
        request_id_var.set(uuid.uuid4().hex[:12])
        trace_id_var.set(trace_id)
        request.state.trace_id = trace_id

        # Buffer body for auditing while keeping it available to handlers.
        body = b""
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            content_length = request.headers.get("content-length")
            try:
                body = await request.body()
            except Exception:
                body = b""
            if request.url.path in ("/api/v1/auth/login", "/api/v1/auth/refresh"):
                body = b""  # never audit credentials

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            scope = dict(request.scope)
            scope["receive"] = receive
            from starlette.requests import Request as SRequest

            request = SRequest(scope)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            cost_ms = int((time.perf_counter() - start) * 1000)
            self._maybe_audit(request, body, cost_ms, trace_id)
        return response

    def _maybe_audit(self, request: Request, body: bytes, cost_ms: int, trace_id: str) -> None:
        if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
            return
        path = request.url.path
        if not path.startswith("/api/v1"):
            return
        if any(path.startswith(p) for p in AUDIT_EXCLUDED_PREFIXES):
            return
        try:
            if body:
                try:
                    params = json.loads(body)
                except Exception:
                    params = {"_raw": body.decode("utf-8", errors="replace")[:2000]}
            else:
                params = None

            db = self.db_factory()
            try:
                user = getattr(request.state, "audit_user", None)
                from app.db.models import AuditLog

                db.execute(
                    AuditLog.__table__.insert().values(
                        user_id=user.id if user else None,
                        username=user.username if user else "",
                        module=path.split("/")[3] if len(path.split("/")) > 3 else "",
                        action=request.method.lower(),
                        method=request.method,
                        path=path,
                        params=_redact(params),
                        ip=request.client.host if request.client else "",
                        user_agent=request.headers.get("user-agent", "")[:255],
                        status=1,
                        cost_ms=cost_ms,
                        trace_id=trace_id,
                    )
                )
                db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
        except Exception:
            pass  # audit must never break the request path
