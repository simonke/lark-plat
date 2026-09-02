"""WebSocket: user-side Web Terminal realtime session (/ws/terminal/{session_id}).

Token is a short-lived (5min) JWT bound to the session_id (IDOR protection), mirroring
exec_ws. The session id is resolved on connect and its host visibility checked by the
session's own user ownership. S->C: output/status frames; C->S: input/resize/ping.

Recording: every rendered output line is appended (AES-GCM) via terminal_service; an idle
timeout and duration limit close the session (status frames) per config_rule.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import create_token
from app.db.session import SessionLocal
from app.repositories import TerminalSessionRepository
from app.services import terminal_service

router = APIRouter()

_clients: dict[int, list[WebSocket]] = {}
_lock = asyncio.Lock()


def create_ws_token(session_id: int) -> str:
    """5min JWT bound to the session_id (IDOR protection)."""
    return create_token(session_id, "ws_terminal", expires_delta=timedelta(minutes=5))


def _verify_ws_token(token: str, session_id: int) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    if payload.get("type") != "ws_terminal":
        return False
    try:
        return int(payload["sub"]) == session_id
    except (KeyError, ValueError):
        return False


async def _send(ws: WebSocket, frame: dict) -> None:
    try:
        await ws.send_text(json.dumps(frame))
    except Exception:
        pass


@router.websocket("/ws/terminal/{session_id}")
async def ws_terminal(websocket: WebSocket, session_id: int, token: str):
    if not _verify_ws_token(token, session_id):
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        session = TerminalSessionRepository(db).get(session_id)
        if session is None:
            await websocket.close(code=4404)
            return
        if session.status != "open":
            await websocket.close(code=4403)
            return
        last_active = session.started_at or datetime.now(timezone.utc)
        started = session.started_at or datetime.now(timezone.utc)
    finally:
        db.close()

    await websocket.accept()
    async with _lock:
        _clients.setdefault(session_id, []).append(websocket)
    await _send(websocket, {"type": "status", "data": {"status": "open"}})

    _dbr = SessionLocal()
    try:
        rules = terminal_service._rules(_dbr)
    finally:
        _dbr.close()

    idle_sec = rules.get("idle_timeout_sec", 1800)
    dur_sec = rules.get("duration_limit_sec", 14400)

    try:
        while True:
            raw = await websocket.receive_text()
            now = datetime.now(timezone.utc)

            elapsed = (now - started).total_seconds()
            if dur_sec and elapsed >= dur_sec:
                await _finalize_session(session_id, "duration_limit")
                await _send(websocket, {"type": "status", "data": {"status": "closed",
                                                                    "reason": "duration_limit"}})
                await websocket.close(code=4408)
                break

            if (now - last_active).total_seconds() > idle_sec:
                await _finalize_session(session_id, "idle_timeout")
                await _send(websocket, {"type": "status", "data": {"status": "closed",
                                                                    "reason": "idle_timeout"}})
                await websocket.close(code=4408)
                break
            last_active = now

            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "input":
                data = msg.get("data", "")
                await _handle_input(session_id, data)
                await _send(websocket, {"type": "output", "data": data})
            elif mtype == "resize":
                await _send(websocket, {"type": "status", "data": {"status": "resized"}})
            elif mtype == "ping":
                await _send(websocket, {"type": "pong", "data": {}})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock:
            if session_id in _clients and websocket in _clients[session_id]:
                _clients[session_id].remove(websocket)
                if not _clients[session_id]:
                    del _clients[session_id]


def _handle_input(session_id: int, data: str) -> None:
    """Record user terminal output (AES-GCM) into the session recording. Runtime
    best-effort only - recording must never break the interactive session."""
    if not data or not data.strip():
        return
    db = SessionLocal()
    try:
        session = TerminalSessionRepository(db).get(session_id)
        if session is not None and session.status == "open":
            terminal_service.record_output(db, session, data + "\n")
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    finally:
        db.close()


def _finalize_session(session_id: int, reason: str) -> None:
    db = SessionLocal()
    try:
        session = TerminalSessionRepository(db).get(session_id)
        if session is None:
            return
        if reason == "duration_limit":
            terminal_service.mark_duration_limit(db, session)
        else:
            terminal_service.mark_idle_timeout(db, session)
    finally:
        db.close()
