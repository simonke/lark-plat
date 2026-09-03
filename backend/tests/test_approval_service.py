"""Stage-4 approval service unit tests (api-design §9 approval).

Pins contract:
  A1  approve: pending -> approved, records timeline, dispatches linked exec task
  A2  approve on already-decided -> ConflictError (state-machine guard)
  A3  approve optimistic-lock conflict -> ConflictError (409)
  A4  approve with missing linked exec task -> NotFoundError + rollback
  A5  reject: pending -> rejected, cancels linked awaiting_approval task
  A6  cancel: only requester/admin may cancel, pending -> canceled
  A7  rules: create validates kind / update / delete (missing -> NotFound)
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.schemas import RuleCreate, RuleUpdate, RuleOut
from app.services import approval_service


class _Db:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def scalar(self, *a, **kw):
        return 1


class _User:
    def __init__(self, uid=1, is_admin=0):
        self.id = uid
        self.is_admin = is_admin
        self.permissions = set()
        self.required = []

    def require_perm(self, code):
        self.required.append(code)
        self.permissions.add(code)

    def has_perm(self, code):
        return code in self.permissions or bool(self.is_admin)


def _approval(status="pending", requester_id=1, version=1):
    return SimpleNamespace(id=1, request_no="AP-1", biz_type="exec", biz_id=10,
                           title="t", reason="r", requester_id=requester_id,
                           sensitive_hit=None, status=status, approver_id=None,
                           decided_at=None, created_at=datetime.now(timezone.utc),
                           version=version)


def _approval_repo(approval, ok=True):
    return SimpleNamespace(
        get=lambda i: approval,
        optimistic_update=lambda *a: ok,
        add=lambda o: None,
    )


def _exec_task(status="awaiting_approval", version=1):
    return SimpleNamespace(id=10, task_no="T-1", version=version, status=status)


def test_a1_approve_transitions_and_dispatches(monkeypatch):
    db = _Db()
    user = _User(uid=2)
    approval = _approval()
    task = _exec_task()
    monkeypatch.setattr(approval_service, "ApprovalRepository", lambda d: _approval_repo(approval))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=lambda *a: True))
    out = approval_service.approve(db, user, 1, "ok")
    assert out == {"id": 1, "status": "approved"}
    assert approval.version == 2
    assert approval.approver_id == 2
    assert db.commits == 1
    assert "approval:approve" in user.required
    assert {r.action for r in db.added if hasattr(r, "action")} == {"approve"}


def test_a2_approve_already_decided_conflict(monkeypatch):
    db = _Db()
    user = _User(uid=2)
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: _approval_repo(_approval(status="approved")))
    with pytest.raises(ConflictError):
        approval_service.approve(db, user, 1, "x")


def test_a3_approve_optimistic_lock_conflict(monkeypatch):
    db = _Db()
    user = _User(uid=2)
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: _approval_repo(_approval(), ok=False))
    with pytest.raises(ConflictError):
        approval_service.approve(db, user, 1, "x")


def test_a4_approve_missing_exec_task_rolls_back(monkeypatch):
    db = _Db()
    user = _User(uid=2)
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: _approval_repo(_approval()))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        approval_service.approve(db, user, 1, "x")
    assert db.rollbacks == 1


def test_a5_reject_cancels_awaiting_task(monkeypatch):
    db = _Db()
    user = _User(uid=2)
    approval = _approval()
    task = _exec_task()
    monkeypatch.setattr(approval_service, "ApprovalRepository", lambda d: _approval_repo(approval))
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=lambda *a: True))
    out = approval_service.reject(db, user, 1, "no")
    assert out == {"id": 1, "status": "rejected"}
    assert approval.version == 2
    assert task.version == 2
    assert task.finished_at is not None


def test_a6_cancel_requires_requester(monkeypatch):
    db = _Db()
    # non-requester, non-admin -> ForbiddenError
    approval = _approval(requester_id=1)
    monkeypatch.setattr(approval_service, "ApprovalRepository",
                        lambda d: _approval_repo(approval))
    other = _User(uid=5)
    with pytest.raises(ForbiddenError):
        approval_service.cancel(db, other, 1)

    # requester -> canceled
    task = _exec_task()
    monkeypatch.setattr(approval_service, "ExecTaskRepository",
                        lambda d: SimpleNamespace(get=lambda i: task,
                                                  optimistic_update=lambda *a: True))
    requester = _User(uid=1)
    out = approval_service.cancel(db, requester, 1)
    assert out == {"id": 1, "status": "canceled"}


def test_a7_rules_crud(monkeypatch):
    db = _Db()
    # invalid kind
    with pytest.raises(BadRequestError):
        approval_service.create_rule(db, RuleCreate(name="x", kind="bad", value={}))
    # valid create
    added = []
    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(add=lambda o: added.append(o) or setattr(o, "id", 3),
                                                  get=lambda i: None))
    monkeypatch.setattr(approval_service, "ApprovalRule", SimpleNamespace)
    rid = approval_service.create_rule(db, RuleCreate(name="k", kind="keyword", value={"w": ["rm"]}))
    assert rid == 3
    assert added and added[0].kind == "keyword"
    # update/delete missing -> NotFound
    monkeypatch.setattr(approval_service, "ApprovalRuleRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        approval_service.update_rule(db, 99, RuleUpdate(name="x"))
    with pytest.raises(NotFoundError):
        approval_service.delete_rule(db, 99)
