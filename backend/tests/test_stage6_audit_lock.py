"""Stage-6 audit middleware coverage lock (US-03/US-11 append-only audit).

Targets coverage holes in app/core/audit_middleware.py:
  AU1  write methods audit; GET does not touch DB
  AU2  non-/api/v1 paths and excluded prefixes skipped
  AU3  JSON body redacted (sensitive/nested), raw fallback for non-JSON
  AU4  audit row carries user/ip/user_agent/trace_id/cost; login body never
       persisted (credentials cleared before audit)
  AU5  writer failure rolls back; db_factory failure never breaks the request
  AU6  _redact recursion on nested dict/list and sensitive keys
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core import audit_middleware as am


class _RecordingDB:
    def __init__(self):
        self.executed = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt):
        self.executed.append(stmt)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


def _params(stmt) -> dict:
    """Bound param values of the audit INSERT (params column is JSONB, so the
    literal-compile route is unavailable - inspect the bound values instead)."""
    return dict(stmt.compile().params)


class _StateMW(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.audit_user = SimpleNamespace(id=7, username="qa-user")
        return await call_next(request)


def _make_app(db_factory):
    async def handler(request):
        return JSONResponse({"ok": True})

    routes = [
        Route("/api/v1/notify/channels", handler, methods=["POST", "GET"]),
        Route("/api/v1/auth/login", handler, methods=["POST"]),
        Route("/api/v1/approvals/1/approve", handler, methods=["POST"]),
        Route("/api/v1/system/roles/1", handler, methods=["DELETE"]),
        Route("/healthz", handler, methods=["POST"]),
        Route("/docs", handler, methods=["POST"]),
        Route("/openapi.json", handler, methods=["POST"]),
        Route("/ws/exec", handler, methods=["POST"]),
        Route("/agent/ws", handler, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(_StateMW)
    app.add_middleware(am.AuditMiddleware, db_factory=db_factory)
    return TestClient(app)


def test_au1_write_methods_audited_get_skipped():
    db = _RecordingDB()
    client = _make_app(lambda: db)

    resp = client.get("/api/v1/notify/channels")
    assert resp.status_code == 200
    assert not db.executed

    resp = client.post("/api/v1/notify/channels", json={"name": "c"})
    assert resp.status_code == 200
    assert len(db.executed) == 1
    assert db.commits == 1
    p = _params(db.executed[0])
    assert p["module"] == "notify"
    assert p["action"] == "post" and p["method"] == "POST"
    assert p["username"] == "qa-user"
    assert p["status"] == 1


def test_au2_skipped_paths_do_not_audit():
    db = _RecordingDB()
    client = _make_app(lambda: db)
    for path in ("/healthz", "/docs", "/openapi.json", "/ws/exec", "/agent/ws"):
        resp = client.post(path)
        assert resp.status_code == 200, path
    assert not db.executed


def test_au3_body_redaction_and_raw_fallback():
    db = _RecordingDB()
    client = _make_app(lambda: db)

    client.post("/api/v1/notify/channels", json={
        "name": "ops",
        "config": {"webhook": "https://x", "secret": "s3cret-value"},
        "tags": [{"k": "v"}],
    })
    redacted = _params(db.executed[0])["params"]
    assert redacted["config"]["secret"] == "***"
    assert redacted["config"]["webhook"] == "https://x"
    assert redacted["name"] == "ops"
    assert "s3cret-value" not in str(redacted)

    db2 = _RecordingDB()
    client2 = _make_app(lambda: db2)
    client2.post("/api/v1/notify/channels",
                 content=b"not-json-at-all", headers={"content-type": "text/plain"})
    assert _params(db2.executed[0])["params"] == {"_raw": "not-json-at-all"}


def test_au4_login_body_never_persisted_and_trace_carried():
    db = _RecordingDB()
    client = _make_app(lambda: db)
    try:
        am.trace_id_var.set("trace-abc-123")
        resp = client.post("/api/v1/auth/login",
                           json={"username": "u", "password": "hunter2"})
    finally:
        am.trace_id_var.set(None)
    assert resp.status_code == 200
    p = _params(db.executed[0])
    assert p["module"] == "auth"
    assert p["trace_id"] == "trace-abc-123"
    assert p["params"] is None
    assert "hunter2" not in str(p)


def test_au5_writer_failure_and_factory_failure_are_safe():
    class FailingDB:
        def execute(self, stmt):
            raise RuntimeError("audit write boom")

        def rollback(self):
            self.rollbacks = getattr(self, "rollbacks", 0) + 1

        def close(self):
            pass

        def commit(self):
            pass

    failing = FailingDB()
    client = _make_app(lambda: failing)
    resp = client.post("/api/v1/approvals/1/approve", json={"comment": "ok"})
    assert resp.status_code == 200
    assert failing.rollbacks == 1

    def boom_factory():
        raise RuntimeError("factory boom")

    client2 = _make_app(boom_factory)
    resp = client2.delete("/api/v1/system/roles/1")
    assert resp.status_code == 200


def test_au6_redact_recursion():
    data = {
        "k1": "visible",
        "password": "p",
        "nested": {"secret": "s", "keep": 1},
        "items": [{"key": "k"}, {"ok": True}],
    }
    out = am._redact(data)
    assert out["password"] == "***"
    assert out["nested"]["secret"] == "***" and out["nested"]["keep"] == 1
    assert out["items"][0]["key"] == "***" and out["items"][1]["ok"] is True
    assert out["k1"] == "visible"
    assert am._redact(None) is None
    assert am._redact({}) == {}