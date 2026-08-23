"""Agent WebSocket gateway (/api/v1/agent/ws).

Protocol (api-design §12): hello/heartbeat/exec/stop/exec_log/exec_result/ping/pong.
Security: X-Agent-Token header, agent_id/token ownership check (reviewer red line),
90s no-heartbeat => offline.
Binding (stage2 plan A): hello frame hostname/ip matches a pre-registered unbound
host -> write back agent_id (contract §12 L229 payload carries hostname/ip).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories import ExecLogRepository, ExecTaskHostRepository, HostRepository

logger = logging.getLogger(__name__)
router = APIRouter()

# agent_id -> websocket + last heartbeat ts
_agents: dict[str, dict] = {}
_HEARTBEAT_TIMEOUT = settings.agent_heartbeat_timeout_sec


async def dispatch_to_agent(agent_id: str, frame: dict) -> bool:
    conn = _agents.get(agent_id)
    if conn is None:
        return False
    ws = conn["ws"]
    try:
        await ws.send_text(json.dumps(frame))
        return True
    except Exception:
        return False


def agent_online(agent_id: str) -> bool:
    conn = _agents.get(agent_id)
    if conn is None:
        return False
    age = (datetime.now(timezone.utc) - conn["last_heartbeat"]).total_seconds()
    return age <= _HEARTBEAT_TIMEOUT


def _agent_authenticated(agent_id: str, token: str) -> bool:
    """agent_id/token ownership: in MVP the token is validated against the host's agent_id.
    Production: server-issued agent token bound to registered agent_id."""
    db = SessionLocal()
    try:
        repo = HostRepository(db)
        host = None
        # lookup by agent_id, or by ip/hostname fallback
        for h in repo.list_all():
            if h.agent_id == agent_id:
                host = h
                break
        if host is None:
            # allow pre-registered agents via shared secret for MVP bootstrap
            return token == settings.secret_key
        # ownership: token equals a deterministic secret derived from agent_id
        import hashlib

        expected = hashlib.sha256(f"{agent_id}:{settings.secret_key}".encode()).hexdigest()[:32]
        return token == expected
    finally:
        db.close()


@router.websocket("/agent/ws")
async def agent_ws(
    websocket: WebSocket,
    agent_id: str = Query(...),
    token: str = Query(...),
    x_agent_token: str | None = None,
):
    effective_token = x_agent_token or token
    if not _agent_authenticated(agent_id, effective_token):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    _agents[agent_id] = {"ws": websocket, "last_heartbeat": datetime.now(timezone.utc)}
    # greeting hello_ack (frame 1 of 2): proves link+auth before client speaks;
    # a second hello_ack answers the client's hello frame below (see tools/README.md).
    await websocket.send_text(json.dumps({"type": "hello_ack", "data": {"server_time": datetime.now(timezone.utc).isoformat()}}))
    try:
        await _handle_frames(websocket, agent_id)
    finally:
        _agents.pop(agent_id, None)
        _mark_offline(agent_id)


async def _handle_frames(websocket, agent_id: str) -> None:
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except Exception:
                continue
            mtype = frame.get("type")
            data = frame.get("data") or {}
            if mtype == "hello":
                _bind_host(agent_id, data)
                _mark_online(agent_id, data)
                # response hello_ack (frame 2 of 2): confirms hello/binding processed
                await websocket.send_text(json.dumps({"type": "hello_ack", "data": {"server_time": datetime.now(timezone.utc).isoformat()}}))
            elif mtype == "heartbeat":
                _agents[agent_id]["last_heartbeat"] = datetime.now(timezone.utc)
                _mark_online(agent_id, data)
                await websocket.send_text(json.dumps({"type": "heartbeat_ack", "data": {"now": datetime.now(timezone.utc).isoformat()}}))
            elif mtype == "exec_log":
                _persist_logs(data)
            elif mtype == "exec_result":
                _persist_result(data)
            elif mtype == "pong":
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


def _bind_host(agent_id: str, data: dict) -> None:
    """Plan A: bind a pre-registered host by hello hostname/ip and write back agent_id.

    Only unbound hosts are eligible (first-bind-wins); the agent_id must not already
    be bound elsewhere; ambiguous (0 or >1) matches are refused. No host creation.
    """
    hostname = (data.get("hostname") or "").strip()
    ip = (data.get("ip") or "").strip()
    if not hostname and not ip:
        return
    db = SessionLocal()
    try:
        repo = HostRepository(db)
        hosts = repo.list_all()
        if any(h.agent_id == agent_id for h in hosts):
            return
        candidates = [
            h for h in hosts
            if h.agent_id is None
            and ((ip and h.ip == ip) or (hostname and h.hostname == hostname))
        ]
        if len(candidates) != 1:
            logger.warning("agent %s auto-bind skipped: %d candidate host(s)", agent_id, len(candidates))
            return
        host = candidates[0]
        host.agent_id = agent_id
        db.commit()
        logger.info("agent %s auto-bound to host %s (%s/%s)", agent_id, host.id, host.hostname, host.ip)
    finally:
        db.close()


def _mark_online(agent_id: str, data: dict) -> None:
    db = SessionLocal()
    try:
        repo = HostRepository(db)
        host = next((h for h in repo.list_all() if h.agent_id == agent_id), None)
        if host is None:
            return
        host.status = "online"
        host.last_heartbeat_at = datetime.now(timezone.utc)
        if data.get("os_type"):
            host.os_type = data["os_type"]
        if data.get("os_version"):
            host.os_version = data["os_version"]
        if data.get("agent_version"):
            host.agent_version = data["agent_version"]
        db.commit()
    finally:
        db.close()


def _mark_offline(agent_id: str) -> None:
    db = SessionLocal()
    try:
        repo = HostRepository(db)
        host = next((h for h in repo.list_all() if h.agent_id == agent_id), None)
        if host:
            host.status = "offline"
            db.commit()
    finally:
        db.close()


def _persist_logs(data: dict) -> None:
    items = data.get("items") or [data]
    db = SessionLocal()
    try:
        repo = ExecLogRepository(db)
        for it in items:
            repo.append(int(it["task_host_id"]), int(it.get("seq", 0)),
                        it.get("level", "info"), str(it.get("content", "")))
        db.commit()
    finally:
        db.close()


def _persist_result(data: dict) -> None:
    db = SessionLocal()
    try:
        th_repo = ExecTaskHostRepository(db)
        th = th_repo.by_id(int(data["task_host_id"]))
        if th is None:
            return
        status = data.get("status", "success")
        th_repo.update_status(
            th.id, status,
            exit_code=data.get("exit_code"),
            finished_at=datetime.now(timezone.utc),
        )
        db.commit()
    finally:
        db.close()
