"""Notify service: channel config (AES-GCM), pluggable Channel implementations,
send records, resend. Lark is MVP-mandatory; email/dingtalk/wecom/webhook pluggable."""

from __future__ import annotations

import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret
from app.db.models import NotifyChannel, NotifyRecord
from app.repositories import NotifyChannelRepository, NotifyRecordRepository
from app import schemas


class BaseChannel:
    type = "base"

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def send(self, target: str, title: str, content: str) -> None:
        raise NotImplementedError


class LarkChannel(BaseChannel):
    """Feishu/Lark custom bot webhook."""

    type = "lark"

    def send(self, target: str, title: str, content: str) -> None:
        webhook = self.config.get("webhook") or target
        if not webhook:
            raise BadRequestError("lark webhook not configured")
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": content}],
            },
        }
        resp = httpx.post(webhook, json=payload, timeout=10)
        resp.raise_for_status()


class EmailChannel(BaseChannel):
    type = "email"

    def send(self, target: str, title: str, content: str) -> None:
        # MVP: smtp sending implemented in production profile; placeholder validates config.
        smtp_host = self.config.get("smtp_host")
        if not smtp_host:
            raise BadRequestError("email smtp not configured")
        raise NotImplementedError("smtp send delegated to production mailer")


class WebhookChannel(BaseChannel):
    type = "webhook"

    def send(self, target: str, title: str, content: str) -> None:
        url = self.config.get("url") or target
        resp = httpx.post(url, json={"title": title, "content": content}, timeout=10)
        resp.raise_for_status()


class DingtalkChannel(BaseChannel):
    type = "dingtalk"

    def send(self, target: str, title: str, content: str) -> None:
        url = self.config.get("webhook") or target
        resp = httpx.post(url, json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}}, timeout=10)
        resp.raise_for_status()


class WecomChannel(BaseChannel):
    type = "wecom"

    def send(self, target: str, title: str, content: str) -> None:
        url = self.config.get("webhook") or target
        resp = httpx.post(url, json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}}, timeout=10)
        resp.raise_for_status()


_CHANNELS: dict[str, type[BaseChannel]] = {
    "lark": LarkChannel,
    "email": EmailChannel,
    "dingtalk": DingtalkChannel,
    "wecom": WecomChannel,
    "webhook": WebhookChannel,
}


def _decrypt_config(channel: NotifyChannel) -> dict[str, Any]:
    try:
        return json.loads(decrypt_secret(channel.config_enc))
    except Exception:
        return {}


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in config.items():
        if isinstance(v, str) and (len(v) > 8 or k in ("webhook", "smtp_password")):
            out[k] = v[:4] + "****"
        else:
            out[k] = v
    return out


def list_channels(db: Session) -> list[dict]:
    return [
        {
            "id": c.id, "name": c.name, "type": c.type, "enabled": c.enabled,
            "config_mask": _mask_config(_decrypt_config(c)),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in NotifyChannelRepository(db).list_all()
    ]


def create_channel(db: Session, data: schemas.ChannelCreate) -> int:
    if data.type not in _CHANNELS:
        raise BadRequestError(f"unsupported channel type: {data.type}")
    channel = NotifyChannel(
        name=data.name, type=data.type,
        config_enc=encrypt_secret(json.dumps(data.config, ensure_ascii=False)),
        enabled=data.enabled,
    )
    NotifyChannelRepository(db).add(channel)
    db.commit()
    return channel.id


def update_channel(db: Session, channel_id: int, data: schemas.ChannelUpdate) -> None:
    repo = NotifyChannelRepository(db)
    channel = repo.get(channel_id)
    if channel is None:
        raise NotFoundError("channel not found")
    if data.name:
        channel.name = data.name
    if data.config is not None:
        channel.config_enc = encrypt_secret(json.dumps(data.config, ensure_ascii=False))
    if data.enabled is not None:
        channel.enabled = data.enabled
    db.commit()


def delete_channel(db: Session, channel_id: int) -> None:
    repo = NotifyChannelRepository(db)
    channel = repo.get(channel_id)
    if channel is None:
        raise NotFoundError("channel not found")
    db.delete(channel)
    db.commit()


def set_channel_status(db: Session, channel_id: int, enabled: int) -> None:
    repo = NotifyChannelRepository(db)
    channel = repo.get(channel_id)
    if channel is None:
        raise NotFoundError("channel not found")
    channel.enabled = enabled
    db.commit()


def send(db: Session, channel_id: int, scene: str, target: str, title: str, content: str) -> dict:
    repo = NotifyChannelRepository(db)
    channel = repo.get(channel_id)
    record_repo = NotifyRecordRepository(db)
    record = NotifyRecord(channel_id=channel_id, scene=scene, target=target, title=title, content=content, status="sent")
    if channel is None or channel.enabled != 1:
        record.status = "failed"
        record.error_msg = "channel disabled or missing"
        record_repo.add(record)
        db.commit()
        return {"ok": False, "reason": record.error_msg}
    try:
        cls = _CHANNELS.get(channel.type)
        if cls is None:
            raise BadRequestError("unsupported channel type")
        cls(_decrypt_config(channel)).send(target, title, content)
        record.sent_at = datetime.now(timezone.utc)
        record.status = "sent"
    except Exception as exc:  # noqa: BLE001
        record.status = "failed"
        record.error_msg = str(exc)[:512]
    record_repo.add(record)
    db.commit()
    return {"ok": record.status == "sent", "reason": record.error_msg}


def test_send(db: Session, channel_id: int, title: str, content: str) -> dict:
    return send(db, channel_id, "test", "", title, content)


def list_records(db: Session, channel_id: int | None, scene: str | None, status: str | None,
                 start, end, page: int, size: int) -> dict:
    filters = {"channel_id": channel_id, "scene": scene, "status": status, "start": start, "end": end}
    rows, total = NotifyRecordRepository(db).search(filters, page, size)
    return {
        "list": [schemas.NotifyRecordOut.model_validate(r).model_dump() for r in rows],
        "total": total, "page": page, "size": size,
    }


def resend(db: Session, record_id: int) -> dict:
    repo = NotifyRecordRepository(db)
    record = repo.get(record_id)
    if record is None:
        raise NotFoundError("record not found")
    result = send(db, record.channel_id, record.scene, record.target, record.title, record.content)
    return result
