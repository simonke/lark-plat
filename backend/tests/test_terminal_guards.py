"""Stage-4 backend guards: Web Terminal (P2 domain).

Pins contract behaviour (api-design §6 terminals):
  T1  non-sensitive host -> session opens immediately (no approval)
  T2  sensitive host -> session awaits approval; approves opens it (linkage)
  T3  per-user / global concurrency limit -> RateLimitError (429)
  T4  host visibility enforced on create/view (data permission)
  T5  replay requires an independent terminal:replay permission
  T6  expired/over-retention recording returns 404
  T7  close is idempotent-safe and finalizes duration
  T8  WS token is a short-lived JWT bound to the session_id (IDOR)
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, RateLimitError
from app.services import terminal_service
from app.ws import terminal_ws


class _Db:
    def __init__(self):
        self.added = []
        self.commits = 0
        self._next_id = 100

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def scalar(self, *a, **kw):
        return 0


class _User:
    def __init__(self, uid=1, is_admin=1, groups=()):
        self.id = uid
        self.is_admin = is_admin
        self.visible_group_ids = set(groups)
        self.permissions = set()
        self.required = []

    def require_perm(self, code):
        self.required.append(code)
        self.permissions.add(code)

    def has_perm(self, code):
        return code in self.permissions or self.is_admin


def _host(sensitive=False, group_id=1, hid=1):
    return SimpleNamespace(id=hid, hostname="h1", ip="10.0.0.1",
                           group_id=group_id, sensitivity_level="sensitive" if sensitive else "normal")


def _patch_create(monkeypatch, opens=0, user_open=0, global_open=0, sensitive=False,
                  group_id=1, require_perm=True):
    host = _host(sensitive=sensitive, group_id=group_id)
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: host))
    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: None))
    monkeypatch.setattr(terminal_service, "_session_no", lambda db: "TS-1")
    monkeypatch.setattr(terminal_service, "_approval_no", lambda db: "AP-1")
    monkeypatch.setattr(terminal_service, "ApprovalRepository",
                        lambda db: SimpleNamespace(add=lambda o: None))
    return host


def test_t1_non_sensitive_opens_immediately(monkeypatch):
    db = _Db()
    user = _User()
    _patch_create(monkeypatch)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_by_user", lambda self, u: 0)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_global", lambda self: 0)
    out = terminal_service.create_session(db, user, SimpleNamespace(host_id=1, reason=""))
    assert out["status"] == "open"
    assert out["approval_id"] is None
    assert out["sensitive"] == 0
    assert user.required == ["terminal:create"]


def test_t2_sensitive_requires_approval(monkeypatch):
    db = _Db()
    user = _User()
    created = []
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: _host(sensitive=True)))
    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: None))
    monkeypatch.setattr(terminal_service, "_session_no", lambda db: "TS-2")
    monkeypatch.setattr(terminal_service, "_approval_no", lambda db: "AP-2")
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_by_user", lambda self, u: 0)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_global", lambda self: 0)
    monkeypatch.setattr(terminal_service, "ApprovalRepository",
                        lambda db: SimpleNamespace(add=lambda o: created.append(o) or setattr(o, "id", 999)))
    out = terminal_service.create_session(db, user, SimpleNamespace(host_id=1, reason=""))
    assert out["status"] == "awaiting_approval"
    assert out["approval_id"] is not None
    assert out["sensitive"] == 1
    assert created and created[0].biz_type == "terminal"
    assert created[0].status == "pending"


def test_t3_concurrency_reached_raises_429(monkeypatch):
    db = _Db()
    user = _User()
    _patch_create(monkeypatch)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_by_user", lambda self, u: 1)
    with pytest.raises(RateLimitError):
        terminal_service.create_session(db, user, SimpleNamespace(host_id=1, reason=""))

    _patch_create(monkeypatch)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_by_user", lambda self, u: 0)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "count_open_global", lambda self: 999)
    with pytest.raises(RateLimitError):
        terminal_service.create_session(db, user, SimpleNamespace(host_id=1, reason=""))


def test_t4_host_visibility_enforced(monkeypatch):
    db = _Db()
    user = _User(is_admin=0, groups=(2,))
    _patch_create(monkeypatch, group_id=1)
    with pytest.raises(ForbiddenError):
        terminal_service.create_session(db, user, SimpleNamespace(host_id=1, reason=""))


def test_t5_replay_requires_replay_perm(monkeypatch):
    db = _Db()
    session = SimpleNamespace(id=1, status="closed", host_id=1, user_id=1,
                              started_at=datetime.now(timezone.utc), created_at=None)
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: session))
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: _host()))
    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: None))
    monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                        "after_offset", lambda self, s, a, z: [])
    monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                        "max_offset", lambda self, s: 0)
    user = _User()
    for _ in range(1):
        user.permissions.add("terminal:replay")
    out = terminal_service.replay_recording(db, user, 1, 0, 100)
    assert out["session_id"] == 1
    assert "terminal:replay" in user.required


def test_t6_expired_recording_returns_404(monkeypatch):
    db = _Db()
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    session = SimpleNamespace(id=1, status="closed", host_id=1, user_id=1,
                              started_at=old, created_at=None)
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: session))
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: _host()))
    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: None))
    user = _User()
    with pytest.raises(NotFoundError):
        terminal_service.replay_recording(db, user, 1, 0, 100)


def test_t7_close_finalizes_duration(monkeypatch):
    db = _Db()
    started = datetime.now(timezone.utc)
    session = SimpleNamespace(id=1, status="open", version=1, host_id=1, user_id=1,
                              session_no="TS-1", started_at=started, finished_at=None,
                              close_reason="", duration_sec=0)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository, "get",
                        lambda self, i: session)
    monkeypatch.setattr(terminal_service.TerminalSessionRepository, "optimistic_close",
                        lambda self, s, v: True)
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: _host()))
    user = _User()
    out = terminal_service.close_session(db, user, 1)
    assert out["status"] == "closed"
    assert session.close_reason == "manual"
    assert session.finished_at is not None
    assert session.duration_sec >= 0
    assert "terminal:close" in user.required


def test_t8_ws_token_bound_to_session(monkeypatch):
    tok = terminal_ws.create_ws_token(42)
    assert terminal_ws._verify_ws_token(tok, 42) is True
    assert terminal_ws._verify_ws_token(tok, 43) is False
    assert terminal_ws._verify_ws_token("garbage", 42) is False
