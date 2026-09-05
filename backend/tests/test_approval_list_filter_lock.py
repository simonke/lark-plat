"""Stage-4 approval contract lock (api-design v2.1 §9, architect frozen 2026-09-05).

Pins the frozen approval contract against regression (independent of caller):
  L1  list: mine=True -> requester_id=user.id, todo=True -> mine_todo=True;
      status/biz_type pass through; response = {list,total,page,size}
  L2  list default (mine=False/todo=False) -> status/biz_type only,
      no requester_id / no mine_todo (contract dropped requester_id=me|all)
  L3  ApproveIn schema fields == {comment} exactly (no version field)
  L4  cancel endpoint takes no request body (comment not accepted)
  L5  approve/reject service take comment only (no version param)

Optimistic-lock conflict -> ConflictError(409) is locked by in-tree A3
(test_approval_service.py); cancel requester/admin guard by A6.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from app.schemas import ApproveIn
from app.services import approval_service


class _Db:
    pass


class _User:
    def __init__(self, uid=1):
        self.id = uid


class _SearchProbe:
    def __init__(self, rows=(), total=0):
        self.filters = None
        self.rows = rows
        self.total = total

    def __call__(self, filters, page, size):
        self.filters = filters
        return list(self.rows), self.total


def _patch_repo(monkeypatch, probe):
    monkeypatch.setattr(
        approval_service, "ApprovalRepository",
        lambda db: SimpleNamespace(search=probe),
    )


def test_l1_mine_and_todo_set_filter_keys(monkeypatch):
    probe = _SearchProbe()
    _patch_repo(monkeypatch, probe)
    user = _User(uid=7)
    out = approval_service.list_approvals(_Db(), user, "pending", "exec", True, True, 1, 10)
    assert out == {"list": [], "total": 0, "page": 1, "size": 10}
    assert probe.filters == {
        "status": "pending",
        "biz_type": "exec",
        "requester_id": 7,
        "mine_todo": True,
    }


def test_l2_mine_only(monkeypatch):
    probe = _SearchProbe()
    _patch_repo(monkeypatch, probe)
    approval_service.list_approvals(_Db(), _User(uid=3), None, None, True, False, 1, 10)
    assert probe.filters["requester_id"] == 3
    assert "mine_todo" not in probe.filters


def test_l2b_todo_only(monkeypatch):
    probe = _SearchProbe()
    _patch_repo(monkeypatch, probe)
    approval_service.list_approvals(_Db(), _User(), None, None, False, True, 1, 10)
    assert probe.filters["mine_todo"] is True
    assert "requester_id" not in probe.filters


def test_l2c_default_no_personal_filters(monkeypatch):
    probe = _SearchProbe()
    _patch_repo(monkeypatch, probe)
    approval_service.list_approvals(_Db(), _User(), None, None, False, False, 1, 10)
    assert probe.filters == {"status": None, "biz_type": None}


def test_l3_approve_in_has_only_comment():
    assert set(ApproveIn.model_fields) == {"comment"}
    assert ApproveIn().comment == ""


def test_l4_cancel_endpoint_has_no_body():
    from app.api.v1.endpoints import approval as ep

    params = set(inspect.signature(ep.cancel).parameters)
    assert params == {"db", "user", "approval_id"}


def test_l5_approve_reject_take_comment_only():
    for fn in (approval_service.approve, approval_service.reject):
        assert set(inspect.signature(fn).parameters) == {"db", "user", "approval_id", "comment"}