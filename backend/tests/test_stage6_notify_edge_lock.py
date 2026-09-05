"""Stage-6 notify coverage lock (US-09, api-design §10). Extends in-tree N1~N7
to branches still uncovered in notify_service.py:
  NB1  BaseChannel.send raises NotImplementedError
  NB2  lark/email channel config guards (BadRequest / NotImplementedError)
  NB3  webhook/dingtalk/wecom channel payload post
  NB4  _decrypt_config failure -> {}; _mask_config masking rules
  NB5  update_channel partial updates; delete_channel success; set_channel_status
  NB6  send channel.send raises -> failed record with error_msg
  NB7  list_records pagination shape; resend missing -> NotFound
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
        self.deleted = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _httpx_fake():
    posted = []

    def post(url, *a, **k):
        posted.append((url, k.get("json")))
        return SimpleNamespace(raise_for_status=lambda: None)

    return SimpleNamespace(post=post), posted


def test_nb1_base_channel_send_raises():
    with pytest.raises(NotImplementedError):
        notify_service.BaseChannel({}).send("t", "T", "C")


def test_nb2_channel_config_guards():
    with pytest.raises(BadRequestError):
        notify_service.LarkChannel({}).send("", "T", "C")
    with pytest.raises(BadRequestError):
        notify_service.EmailChannel({}).send("t", "T", "C")
    with pytest.raises(NotImplementedError):
        notify_service.EmailChannel({"smtp_host": "smtp.example"}).send("t", "T", "C")


def test_nb3_pluggable_channels_post_expected_payloads(monkeypatch):
    http, posted = _httpx_fake()
    monkeypatch.setattr(notify_service, "httpx", http)
    notify_service.WebhookChannel({"url": "https://w"}).send("t", "T", "C")
    notify_service.DingtalkChannel({"webhook": "https://d"}).send("t", "T", "C")
    notify_service.WecomChannel({"webhook": "https://we"}).send("t", "T", "C")

    urls = [p[0] for p in posted]
    assert urls == ["https://w", "https://d", "https://we"]
    assert posted[0][1] == {"title": "T", "content": "C"}
    assert posted[1][1]["msgtype"] == "text"
    assert posted[2][1]["msgtype"] == "text"


def test_nb4_decrypt_and_mask(monkeypatch):
    monkeypatch.setattr(notify_service, "decrypt_secret", lambda s: '{"a": 1}')
    assert notify_service._decrypt_config(SimpleNamespace(config_enc="enc")) == {"a": 1}
    monkeypatch.setattr(notify_service, "decrypt_secret", lambda s: (_ for _ in ()).throw(ValueError()))
    assert notify_service._decrypt_config(SimpleNamespace(config_enc="bad")) == {}

    masked = notify_service._mask_config({
        "webhook": "https://very-long-webhook.example/x",
        "smtp_password": "supersecret",
        "short": "ab",
        "seed": "123456789",
    })
    assert masked["webhook"] == "http****"
    assert masked["smtp_password"] == "supe****"
    assert masked["short"] == "ab"
    assert masked["seed"] == "1234****"


def test_nb5_update_delete_status(monkeypatch):
    db = _Db()
    channel = SimpleNamespace(id=1, name="c", config_enc="old", enabled=1)
    enc_calls = []
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: channel,
                                                  delete=lambda o: None))
    monkeypatch.setattr(notify_service, "encrypt_secret",
                        lambda s: enc_calls.append(s) or f"ENC:{s}")

    notify_service.update_channel(db, 1, SimpleNamespace(name="c2", config=None, enabled=None))
    assert channel.name == "c2"
    assert not enc_calls

    notify_service.update_channel(db, 1, SimpleNamespace(name="c3", config={"k": 1}, enabled=0))
    assert channel.name == "c3" and channel.enabled == 0
    assert enc_calls and enc_calls[-1] == '{"k": 1}'

    notify_service.delete_channel(db, 1)
    notify_service.set_channel_status(db, 1, 0)
    assert channel.enabled == 0
    assert db.deleted == [channel]
    assert db.commits == 4

    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: None))
    with pytest.raises(NotFoundError):
        notify_service.delete_channel(db, 9)
    with pytest.raises(NotFoundError):
        notify_service.set_channel_status(db, 9, 1)


def test_nb6_send_exception_marks_failed(monkeypatch):
    db = _Db()
    records = []

    class _RecRepo:
        def get(self, rid):
            return None

        def add(self, obj):
            records.append(obj)

    class BoomChannel(notify_service.BaseChannel):
        def send(self, target, title, content):
            raise RuntimeError("webhook unreachable")

    monkeypatch.setattr(notify_service, "_CHANNELS", {"lark": BoomChannel})
    monkeypatch.setattr(notify_service, "NotifyChannelRepository",
                        lambda d: SimpleNamespace(get=lambda i: SimpleNamespace(
                            id=1, enabled=1, type="lark", config_enc="enc")))
    monkeypatch.setattr(notify_service, "NotifyRecordRepository", lambda d: _RecRepo())
    monkeypatch.setattr(notify_service, "decrypt_secret", lambda s: "{}")
    out = notify_service.send(db, 1, "exec", "t", "T", "C")
    assert out["ok"] is False
    assert records and records[0].status == "failed"
    assert "webhook unreachable" in records[0].error_msg


def test_nb7_list_records_and_resend_missing(monkeypatch):
    row = SimpleNamespace(id=1, channel_id=2, scene="exec", target="t", title="T",
                          content="C", status="sent", error_msg=None, sent_at=None,
                          created_at=datetime.now(timezone.utc))
    monkeypatch.setattr(notify_service, "NotifyRecordRepository",
                        lambda d: SimpleNamespace(
                            search=lambda f, page, size: ([row], 1),
                            get=lambda i: None))
    out = notify_service.list_records(_Db(), None, None, None, None, None, 1, 10)
    assert out["total"] == 1 and out["page"] == 1 and out["size"] == 10
    assert out["list"][0]["scene"] == "exec"

    with pytest.raises(NotFoundError):
        notify_service.resend(_Db(), 99)