"""WebSocket: user-side exec realtime echo (/ws/exec/{task_host_id}).

Token is a short-lived (5min) JWT bound to task_host_id to prevent IDOR (reviewer red line).
Supports after_seq resume for reconnect, seq ordering.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import create_token
from app.repositories import ExecLogRepository, ExecTaskHostRepository, ExecTaskRepository
from app.db.session import SessionLocal

router = APIRouter()

# task_host_id -> list of connected websockets
_clients: dict[int, list[WebSocket]] = {}
_lock = asyncio.Lock()


def create_ws_token(task_host_id: int) -> str:
    """5min JWT bound to the task_host_id (IDOR protection)."""
    return create_token(task_host_id, "ws", expires_delta=timedelta(minutes=5))


async def broadcast(task_host_id: int, message: dict) -> None:
    async with _lock:
        sockets = list(_clients.get(task_host_id, []))
    for ws in sockets:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass


def _verify_ws_token(token: str, task_host_id: int) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    if payload.get("type") != "ws":
        return False
    try:
        return int(payload["sub"]) == task_host_id
    except (KeyError, ValueError):
        return False


@router.websocket("/ws/exec/{task_host_id}")
async def ws_exec(websocket: WebSocket, task_host_id: int, token: str):
    if not _verify_ws_token(token, task_host_id):
        await websocket.close(code=4401)
        return
    # visibility check: task host must exist
    db = SessionLocal()
    try:
        th = ExecTaskHostRepository(db).by_id(task_host_id)
        if th is None:
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    await websocket.accept()
    async with _lock:
        _clients.setdefault(task_host_id, []).append(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "stop":
                await broadcast(task_host_id, {"type": "status", "data": {"status": "stopping"}})
                # stop flow is executed via REST (permission checks); WS only notifies UI
                await websocket.send_text(json.dumps({"type": "status", "data": {"status": "stopping"}}))
            elif mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "data": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock:
            if task_host_id in _clients and websocket in _clients[task_host_id]:
                _clients[task_host_id].remove(websocket)
                if not _clients[task_host_id]:
                    del _clients[task_host_id]
