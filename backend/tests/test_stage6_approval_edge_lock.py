"""Stage-6 approval coverage lock (US-06, api-design §9). Extends in-tree A1~A7
to branches still uncovered in approval_service.py:
  B1  _approval_no count+1 / default 0001
  B2  detail builds timeline
  B3  approve on missing approval -> NotFound; approve terminal linkage activates
  B4  approve exec dispatch.delay exception swallowed; exec optimistic-update
      failure -> ConflictError + rollback
  B5  reject tolerates missing awaiting task; cancels awaiting->canceled
  B6  cancel optimistic-lock conflict -> ConflictError; cancel cancels awaiting task
  B7  list_rules enabled list; update_rule sets fields; delete_rule removes
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.schemas import RuleUpdate
from app.services import approval_service
from app.services import terminal_service as ts


class _Db:
    def __init__(self):
        self.added = []
        self.deleted = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def scalar(self, *a, **kw):
        return 5


class _User:
    def __init__(self, uid=2, is_admin=0):
        self.id = uid
        self.is_admin = is_admin
        self.permissions = set()
        self.required = []

    def require_perm(self, code):
        self.required.append(code)
        self.permissions.add(code)

    def has_perm(self, code):
        return code in self.permissions or bool(self.is_admin)


def _approval(status="pending", requester_id=1, biz_type="exec", version=1):
    return SimpleNamespace(id=1, request_no="AP-1", biz_type=biz_type, biz_id=10,
                           title="t", reason="r", requester_id=requester_id,
                           sensitive_hit=None, status=status, approver_id=None,
                           decided_at=None, created_at=datetime.now(timezone.utc),
                           version=version)


def _exec_task(status="awaiting_approval", version=1):
    return SimpleNamespace(id=10, task_no="T-1", version=version, status=status,
                           started_at=None, finished_at=None)


class _SeqDb(_Db):
    """Sequence-backed session (B1): execute() returns scalar from a counter,
    mirroring the in-tree _SeqDb in test_no_generation_guards.py so the lock
    survives the sequence-generation rework (db.execute(text(nextval)).scalar())."""

    def __init__(self, counter=0):
        super().__init__()
        self._counter = counter

    def execute(self, stmt):
        self._counter += 1
        n = self._counter
        return SimpleNamespace(scalar=lambda: n)


def test_b1_approval_no_counts():
    assert approval_service._approval_no(_SeqDb(5)) == f"AP-{date.today():%Y%m%d}-0006"
    assert approval_service._approval_no(_SeqDb(0)) == f"AP-{date.today():%Y%m%d}-0001"


def test_b2_detail_builds_timeline(monkeypatch):
    db = _Db()
    rec = SimpleNamespace(action="approve", operator_id=2, comment="ok",
                          created_at=datetime.now(timezone.utc))
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: _approval(),
                                                  search=lambda *a: ([_approval()], 1)))
    monkeypatch.setattr(approval_service, "ApprovalRecordRepository",
                        lambda d: SimpleNamespace(timeline=lambda i: [rec]))
    out = approval_service.detail(db, 1)
    assert out["id"] == 1
    assert out["timeline"] == [
        {"action": "approve", "operator_id": 2, "comment": "ok",
         "created_at": rec.created_at.isoformat()}
    ]


def test_b3_approve_missing_not_found_and_terminal_linkage(monkeypatch):
    db = _Db()
    user = _User()
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        approval_service.approve(db, user, 1, "x")

    activated = []

    def fake_activate(d, a):
        activated.append(a)

    monkeypatch.setattr(ts, "activate_on_approval", fake_activate)
    approval = _approval(biz_type="terminal")
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: approval,
                                                  optimistic_update=lambda *a: True))
    out = approval_service.approve(db, user, 1, "ok")
    assert out["status"] == "approved"
    assert activated and activated[0] is approval


def test_b4_approve_dispatch_swallowed_and_exec_conflict(monkeypatch):
    db = _Db()
    user = _User()

    def raiser(self):
        raise RuntimeError("broker down")

    raiser_obj = SimpleNamespace(delay=raiser)
    monkeypatch.setattr("app.tasks.exec_tasks.exec_dispatch", raiser_obj)
    approval = _approval()
    task = _exec_task()
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: approval,
                                                  optimistic_update=lambda *a: True))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=lambda *a: True))
    out = approval_service.approve(db, user, 1, "ok")
    assert out["status"] == "approved"
    assert db.commits == 1

    db2 = _Db()
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: _approval(),
                                                  optimistic_update=lambda *a: True))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: _exec_task(),
                                                  optimistic_update=lambda *a: False))
    with pytest.raises(ConflictError):
        approval_service.approve(db2, user, 1, "ok")
    assert db2.rollbacks == 1


def test_b5_reject_missing_task_tolerated_and_task_canceled(monkeypatch):
    db = _Db()
    user = _User()
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: _approval(),
                                                  optimistic_update=lambda *a: True))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))

    out = approval_service.reject(db, user, 1, "no")
    assert out["status"] == "rejected"

    task = _exec_task()
    calls = []
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(
                            get=lambda i: task,
                            optimistic_update=lambda t, f, to, v: calls.append((t, f, to, v)) or True))
    out = approval_service.reject(db, user, 1, "no")
    assert out["status"] == "rejected"
    assert calls and calls[0][0] == 10
    assert task.version == 2
    assert task.finished_at is not None


def test_b6_cancel_conflict_and_task_canceled(monkeypatch):
    db = _Db()
    requester = _User(uid=1)
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: _approval(),
                                                  optimistic_update=lambda *a: False))
    with pytest.raises(ConflictError):
        approval_service.cancel(db, requester, 1)

    task = _exec_task()
    calls = []
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: SimpleNamespace(get=lambda i: _approval(),
                                                  optimistic_update=lambda *a: True))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(
                            get=lambda i: task,
                            optimistic_update=lambda t, f, to, v: calls.append((t, f, to, v)) or True))
    out = approval_service.cancel(db, requester, 1)
    assert out["status"] == "canceled"
    assert calls and calls[0][1:3] == ("awaiting_approval", "canceled")
    assert task.version == 2
    assert task.finished_at is not None


def test_b7_rules_list_update_delete(monkeypatch):
    rule = SimpleNamespace(id=1, name="k", kind="keyword", value={"w": ["rm"]},
                           enabled=1, created_at=datetime.now(timezone.utc))
    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(enabled=lambda: [rule],
                                                  list_all=lambda: [rule]))
    out = approval_service.list_rules(_Db())
    assert out and out[0]["name"] == "k"
    assert out[0]["id"] == 1

    updated = SimpleNamespace(name="k", value={"w": ["rm"]}, enabled=1)
    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(get=lambda i: updated,
                                                  delete=lambda o: None))
    approval_service.update_rule(_Db(), 1, RuleUpdate(name="k2", value={"w": ["pwd"]}, enabled=0))
    assert updated.name == "k2" and updated.value == {"w": ["pwd"]} and updated.enabled == 0

    db = _Db()
    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(get=lambda i: updated,
                                                  delete=lambda o: None))
    approval_service.delete_rule(db, 1)
    assert db.deleted == [updated]
    assert db.commits == 1

    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        approval_service.delete_rule(db, 99)