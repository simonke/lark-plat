"""Agent WebSocket gateway (/api/v1/agent/ws).

Protocol (api-design §12): hello/heartbeat/exec/stop/exec_log/exec_result/ping/pong.
Security: X-Agent-Token header, agent_id/token ownership check (reviewer red line),
90s no-heartbeat => offline.
Binding (stage2 plan A): hello frame hostname/ip matches a pre-registered unbound
host -> write back agent_id (contract §12 L229 payload carries hostname/ip).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.db.session import SessionLocal
from app.repositories import (
    ExecLogRepository,
    ExecTaskHostRepository,
    ExecTaskRepository,
    HostRepository,
)
from app.ws.exec_ws import broadcast

logger = logging.getLogger(__name__)
router = APIRouter()

# agent_id -> websocket + last heartbeat ts
_agents: dict[str, dict] = {}
_HEARTBEAT_TIMEOUT = settings.agent_heartbeat_timeout_sec
_APP_LOOP: asyncio.AbstractEventLoop | None = None


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


def dispatch_to_agent_sync(agent_id: str, frame: dict) -> bool:
    """Thread-safe agent dispatch from sync contexts (worker threads / celery).

    Real frame delivery requires the agent gateway loop in this process; when no
    loop is alive we return False so callers fall back to the mock/degraded path.
    """
    conn = _agents.get(agent_id)
    if conn is None:
        return False
    loop = conn.get("loop") or _APP_LOOP
    if loop is None or loop.is_closed():
        return False
    try:
        fut = asyncio.run_coroutine_threadsafe(dispatch_to_agent(agent_id, frame), loop)
        fut.add_done_callback(lambda f: None)
        return True
    except Exception:
        return False


def agent_online(agent_id: str) -> bool:
    conn = _agents.get(agent_id)
    if conn is None:
        return False
    age = (datetime.now(timezone.utc) - conn["last_heartbeat"]).total_seconds()
    return age <= _HEARTBEAT_TIMEOUT


def task_has_inprocess_agent(db, task_id: int) -> bool:
    """True when any target host of the task is bound to a live agent in THIS
    process. The exec frames must then be dispatched in-process so they reach the
    connected agent gateway (celery runs in a separate process)."""
    for th in ExecTaskHostRepository(db).by_task(task_id):
        host = HostRepository(db).get(th.host_id) if th.host_id else None
        if host and host.agent_id and agent_online(host.agent_id):
            return True
    return False


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
    global _APP_LOOP
    _APP_LOOP = asyncio.get_running_loop()
    _agents[agent_id] = {"ws": websocket, "last_heartbeat": datetime.now(timezone.utc), "loop": _APP_LOOP}
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
                await _persist_logs(data)
            elif mtype == "exec_result":
                await _persist_result(data)
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


async def _persist_logs(data: dict) -> None:
    items = data.get("items") or [data]
    db = SessionLocal()
    try:
        repo = ExecLogRepository(db)
        for it in items:
            task_host_id = int(it["task_host_id"])
            seq = int(it.get("seq", 0))
            level = it.get("level", "info")
            content = str(it.get("content", ""))
            repo.append(task_host_id, seq, level, content)
            await broadcast(task_host_id, {
                "type": "log",
                "data": {"seq": seq, "level": level, "content": content,
                         "created_at": datetime.now(timezone.utc).isoformat()},
            })
        db.commit()
    finally:
        db.close()


async def _persist_result(data: dict) -> None:
    db = SessionLocal()
    try:
        th_repo = ExecTaskHostRepository(db)
        th = th_repo.by_id(int(data["task_host_id"]))
        if th is None:
            return
        status = data.get("status", "success")
        if status == "stopped":
            status = "canceled"
        if status not in ("success", "failed", "timed_out", "canceled"):
            status = "failed"
        exit_code = data.get("exit_code")
        finished_at = datetime.now(timezone.utc)
        th_repo.update_status(th.id, status, exit_code=exit_code, finished_at=finished_at)
        db.commit()
        await broadcast(th.id, {"type": "status", "data": {"status": status, "exit_code": exit_code}})
        await broadcast(th.id, {"type": "result", "data": {
            "task_host_id": th.id, "host_id": th.host_id, "hostname": th.hostname,
            "status": status, "exit_code": exit_code, "finished_at": finished_at.isoformat(),
        }})
        _maybe_finalize_task(db, th.exec_task_id)
    finally:
        db.close()


def _maybe_finalize_task(db, exec_task_id: int) -> None:
    """End-of-run aggregation: when every host reached a terminal state, flip the
    task to the aggregate status (otherwise leave it running for the agent loop)."""
    task = ExecTaskRepository(db).get(exec_task_id)
    if task is None or task.status not in ("running", "pending"):
        return
    th_repo = ExecTaskHostRepository(db)
    stats = th_repo.stats(exec_task_id)
    if not stats:
        return
    active = stats.get("running", 0) + stats.get("pending", 0)
    if active > 0:
        return
    success = stats.get("success", 0)
    failed = stats.get("failed", 0)
    timed = stats.get("timed_out", 0)
    total = sum(stats.values())
    if failed == 0 and timed == 0 and total > 0 and success == total:
        new_status = "success"
    elif failed == 0 and timed == 0 and success > 0:
        new_status = "partial"
    else:
        new_status = "failed"
    if task.status not in (new_status, "canceled", "timed_out"):
        if not ExecTaskRepository(db).optimistic_update(
            exec_task_id, task.status, new_status, task.version
        ):
            return
        task.status = new_status
        task.version += 1
        task.finished_at = datetime.now(timezone.utc)
        db.commit()
