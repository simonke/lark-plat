"""Stage-4 notify service unit tests (api-design §10 notify).

Pins contract:
  N1  create_channel validates type + AES-GCM encrypts config
  N2  send on disabled/missing channel -> failed record, ok=False
  N3  send on lark channel posts card webhook and records sent_at
  N4  send on unsupported channel -> failed record
  N5  resend re-invokes send and records a new result
  N6  update/delete on missing channel -> NotFoundError
  N7  list_channels masks secrets in config_mask
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app.services import notify_service


class _Db:
    def __init__(self):
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _channel(ctype="lark", enabled=1, id=1, cid_enc="enc"):
    return SimpleNamespace(id=id, name="c", type=ctype, enabled=enabled,
                           config_enc=cid_enc,
                           created_at=datetime.now(timezone.utc))


def _record(id=1, channel_id=1, scene="exec", target="t", title="T", content="C", status="sent"):
    return SimpleNamespace(id=id, channel_id=channel_id, scene=scene, target=target,
                           title=title, content=content, status=status,
                           error_msg=None, sent_at=None)


class _RecRepo:
    def __init__(self):
        self.records = []
        self._next = 1

    def get(self, rid):
        return next((r for r in self.records if r.id == rid), None)

    def add(self, obj):
        obj.id = self._next
        self._next += 1
        self.records.append(obj)


def test_n1_create_channel_validates_type_and_encrypts(monkeypatch):
    db = _Db()
    added = []

    class _EncRepo:
        def __init__(self, d):
            pass

        def add(self, obj):
            obj.id = 7
            added.append(obj)

    monkeypatch.setattr(notify_service, "NotifyChannelRepository", _EncRepo)
    monkeypatch.setattr(notify_service, "encrypt_secret", lambda s: f"ENC:{s}")
    out = notify_service.create_channel(db, SimpleNamespace(
        name="ops", type="lark", config={"webhook": "https://x"}, enabled=1))
    assert out == 7
    assert added[0].config_enc.startswith("ENC:")

    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(add=lambda o: None))
    with pytest.raises(BadRequestError):
        notify_service.create_channel(db, SimpleNamespace(
            name="x", type="badtype", config={}, enabled=1))


def test_n2_send_disabled_channel_records_failed(monkeypatch):
    db = _Db()
    rec_repo = _RecRepo()
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: _channel(enabled=0)))
    monkeypatch.setattr(notify_service, "NotifyRecordRepository", lambda d: rec_repo)
    out = notify_service.send(db, 1, "exec", "t", "T", "C")
    assert out["ok"] is False
    assert rec_repo.records and rec_repo.records[0].status == "failed"


def test_n3_send_lark_posts_card_and_records_sent(monkeypatch):
    db = _Db()
    rec_repo = _RecRepo()
    posted = []
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: _channel(enabled=1)))
    monkeypatch.setattr(notify_service, "NotifyRecordRepository", lambda d: rec_repo)
    monkeypatch.setattr(notify_service, "decrypt_secret", lambda s: '{"webhook": "https://lark"}')
    monkeypatch.setattr(notify_service, "httpx",
                        SimpleNamespace(post=lambda *a, **k: (posted.append((a, k)) or SimpleNamespace(
                            raise_for_status=lambda: None))))
    out = notify_service.send(db, 1, "exec", "t", "T", "C")
    assert out["ok"] is True
    assert posted and posted[0][0] == ("https://lark",)
    assert rec_repo.records and rec_repo.records[0].status == "sent"


def test_n4_send_unsupported_channel_fails(monkeypatch):
    db = _Db()
    rec_repo = _RecRepo()
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: _channel(ctype="who")) )
    monkeypatch.setattr(notify_service, "NotifyRecordRepository", lambda d: rec_repo)
    out = notify_service.send(db, 1, "exec", "t", "T", "C")
    assert out["ok"] is False
    assert rec_repo.records[0].status == "failed"


def test_n5_resend_reinvokes_send(monkeypatch):
    db = _Db()
    rec_repo = _RecRepo()
    done = {"n": 0}

    def fake_send(*a, **k):
        done["n"] += 1
        return {"ok": True, "reason": None}

    monkeypatch.setattr(notify_service, "NotifyRecordRepository", lambda d: rec_repo)
    rec_repo.records.append(_record(id=3, status="failed"))
    monkeypatch.setattr(notify_service, "send", fake_send)
    out = notify_service.resend(db, 3)
    assert out["ok"] is True
    assert done["n"] == 1


def test_n6_update_delete_missing_channel_not_found(monkeypatch):
    db = _Db()
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        notify_service.update_channel(db, 99, SimpleNamespace(name="x", config=None, enabled=None))
    with pytest.raises(NotFoundError):
        notify_service.delete_channel(db, 99)


def test_n7_list_channels_masks_config(monkeypatch):
    db = _Db()
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(list_all=lambda: [_channel(enabled=1)]))
    monkeypatch.setattr(notify_service, "decrypt_secret",
                        lambda s: '{"webhook": "https://long-webhook.example/x"}')
    out = notify_service.list_channels(db)
    assert len(out) == 1
    assert "****" in out[0]["config_mask"]["webhook"]
    assert "https://long-webhook" not in out[0]["config_mask"]["webhook"]
