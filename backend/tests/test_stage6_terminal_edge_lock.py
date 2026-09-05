"""Stage-6 terminal coverage lock (US-12, api-design §6 terminals). Extends in-tree
T1~T11 to branches still uncovered in terminal_service.py:
  TB1  _rules override from config_rule values
  TB2  issue_token: not-open -> BadRequest; success binds ws_token/expires_in
  TB3  get_session / list_sessions non-admin user filter
  TB4  close awaiting_approval cancels pending approval
  TB5  close already-closed / optimistic-close conflict -> BadRequest
  TB6  replay: chunk decrypt failure -> ""; has_more gating
  TB7  record_output empty no-op; idle/duration finalize; optimistic close fail
  TB8  activate_on_approval: non-terminal / missing-session no-ops
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.services import terminal_service
from app.ws import terminal_ws


class _Db:
    def __init__(self):
        self.commits = 0

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


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


def _session(status="open", user_id=1, version=1, started=True, sensitive=0):
    return SimpleNamespace(id=1, session_no="TS-1", host_id=1, user_id=user_id,
                           status=status, close_reason=None, sensitive=sensitive,
                           approval_id=None, version=version,
                           started_at=datetime.now(timezone.utc) if started else None,
                           finished_at=None, duration_sec=0, bytes_out=0, bytes_in=0)


class _SessionRepo:
    session = None
    _optimistic_result = True
    _search_fn = None

    def __init__(self, db):
        self.db = db

    def get(self, session_id):
        return _SessionRepo.session

    def optimistic_close(self, session_id, version):
        return _SessionRepo._optimistic_result

    def search(self, filters, page, size):
        fn = _SessionRepo._search_fn
        if fn is not None:
            return fn(filters, page, size)
        return ([_SessionRepo.session], 1)


def _patch_session_repo(monkeypatch, session, optimistic_close=True):
    _SessionRepo.session = session
    _SessionRepo._optimistic_result = optimistic_close
    _SessionRepo._search_fn = None
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository", _SessionRepo)


def test_tb1_rules_override(monkeypatch):
    by_key = {}
    for k in ("terminal_user_concurrency_limit", "terminal_global_concurrency_limit",
              "terminal_idle_timeout_sec", "terminal_duration_limit_sec",
              "terminal_retention_days"):
        by_key[k] = SimpleNamespace(rule_value={"value": 7})
    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: by_key.get(k)))
    rules = terminal_service._rules(_Db())
    assert rules == {"user_limit": 7, "global_limit": 7, "idle_timeout_sec": 7,
                     "duration_limit_sec": 7, "retention_days": 7}

    monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                        lambda db: SimpleNamespace(by_key=lambda k: None))
    rules = terminal_service._rules(_Db())
    assert rules["retention_days"] == 30 and rules["user_limit"] == 1


def test_tb2_issue_token(monkeypatch):
    _patch_session_repo(monkeypatch, _session(status="closed"))
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: None))
    with pytest.raises(BadRequestError):
        terminal_service.issue_token(_Db(), _User(), 1)

    issued = []

    def fake_create(sid):
        issued.append(sid)
        return "ws.jwt.token"

    _patch_session_repo(monkeypatch, _session(status="open"))
    monkeypatch.setattr(terminal_ws, "create_ws_token", fake_create)
    user = _User()
    out = terminal_service.issue_token(_Db(), user, 1)
    assert out == {"session_id": 1, "session_no": "TS-1",
                   "ws_token": "ws.jwt.token", "expires_in": 300}
    assert issued == [1]
    assert "terminal:view" in user.required


def test_tb3_get_session_and_list_non_admin(monkeypatch):
    _patch_session_repo(monkeypatch, _session())
    out = terminal_service.get_session(_Db(), _User(), 1)
    assert out["session_no"] == "TS-1"

    captured = []
    _SessionRepo._search_fn = lambda f, page, size: (captured.append(f) or ([], 0))
    terminal_service.list_sessions(_Db(), _User(is_admin=0, uid=2), None, 1, 10)
    assert captured and captured[0]["user_id"] == 2


def test_tb4_close_awaiting_cancels_approval(monkeypatch):
    db = _Db()
    session = _session(status="awaiting_approval")
    session.approval_id = 9
    approval = SimpleNamespace(id=9, status="pending", version=1)
    updates = []
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: None))
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: session,
                                                   optimistic_close=lambda s, v: True))
    monkeypatch.setattr(terminal_service, "ApprovalRepository",
                        lambda db: SimpleNamespace(get=lambda i: approval,
                                                   optimistic_update=lambda *a: updates.append(a) or True))
    out = terminal_service.close_session(db, _User(), 1)
    assert out["status"] == "closed"
    assert session.close_reason == "canceled_before_approval"
    assert session.status == "closed"
    assert updates and updates[0][0] == 9
    assert db.commits == 1


def test_tb5_close_invalid_states(monkeypatch):
    _patch_session_repo(monkeypatch, _session(status="closed"))
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: None))
    with pytest.raises(BadRequestError):
        terminal_service.close_session(_Db(), _User(), 1)

    _patch_session_repo(monkeypatch, _session(status="open", version=1), optimistic_close=False)
    with pytest.raises(BadRequestError):
        terminal_service.close_session(_Db(), _User(), 1)


def test_tb6_replay_chunks(monkeypatch):
    def case(decrypt_result=None, decrypt_raises=False):
        db = _Db()
        session = _session(status="closed")
        chunks = [SimpleNamespace(offset=1, data_enc="enc", created_at=datetime.now(timezone.utc))]
        monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                            lambda d: SimpleNamespace(get=lambda i: session))
        monkeypatch.setattr(terminal_service, "HostRepository",
                            lambda d: SimpleNamespace(get=lambda i: _host_fake()))
        monkeypatch.setattr(terminal_service, "ConfigRuleRepository",
                            lambda d: SimpleNamespace(by_key=lambda k: None))
        monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                            "after_offset", lambda self, s, a, z: chunks)
        monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                            "max_offset", lambda self, s: 5)

        def dec(s):
            if decrypt_raises:
                raise ValueError("bad blob")
            return decrypt_result

        monkeypatch.setattr(terminal_service, "_decrypt_chunk", dec)
        user = _User()
        user.permissions.add("terminal:replay")
        return terminal_service.replay_recording(db, user, 1, 0, 1)

    out = case(decrypt_result="hello")
    assert out["chunks"][0]["data"] == "hello"
    assert out["has_more"] is True
    assert out["size"] == 1

    out2 = case(decrypt_raises=True)
    assert out2["chunks"][0]["data"] == ""


def test_tb7_record_output_and_finalize(monkeypatch):
    written = []
    monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                        "append", lambda self, s, o, e: written.append((s, o, e)))
    monkeypatch.setattr(terminal_service.TerminalRecordingRepository,
                        "max_offset", lambda self, s: 0)
    monkeypatch.setattr(terminal_service, "encrypt_secret", lambda s: "enc")

    session = SimpleNamespace(id=1, bytes_out=0)
    terminal_service.record_output(_Db(), session, "")
    assert not written

    terminal_service.record_output(_Db(), session, "abc")
    assert written == [(1, 1, "enc")]
    assert session.bytes_out == 3

    idle = _session(status="closed")
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "optimistic_close", lambda self, s, v: True)
    terminal_service.mark_idle_timeout(_Db(), idle)
    assert idle.status == "closed"

    limit = _session(status="open")
    monkeypatch.setattr(terminal_service.TerminalSessionRepository,
                        "optimistic_close", lambda self, s, v: False)
    terminal_service.mark_duration_limit(_Db(), limit)
    assert limit.status == "open"


def test_tb8_activate_on_approval_noops(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not touch repo")

    monkeypatch.setattr(terminal_service, "TerminalSessionRepository", boom)
    terminal_service.activate_on_approval(_Db(), SimpleNamespace(biz_type="exec", biz_id=1))

    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: None))
    terminal_service.activate_on_approval(_Db(), SimpleNamespace(biz_type="terminal", biz_id=1))

    not_awaiting = _session(status="open")
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: not_awaiting))
    terminal_service.activate_on_approval(_Db(), SimpleNamespace(biz_type="terminal", biz_id=1))
    assert not_awaiting.status == "open"


def test_tb9_visibility_guard_branches(monkeypatch):
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        terminal_service._require_visible_session(_Db(), _User(), 1)

    session = _session(user_id=2)
    monkeypatch.setattr(terminal_service, "TerminalSessionRepository",
                        lambda db: SimpleNamespace(get=lambda i: session))
    monkeypatch.setattr(terminal_service, "HostRepository",
                        lambda db: SimpleNamespace(get=lambda i: SimpleNamespace(
                            id=1, group_id=1)))
    with pytest.raises(ForbiddenError):
        terminal_service._require_visible_session(
            _Db(), _User(is_admin=0, uid=1, groups=(2,)), 1)


def _host_fake():
    return SimpleNamespace(id=1, hostname="h", ip="10.0.0.1", group_id=1,
                           sensitivity_level="normal")