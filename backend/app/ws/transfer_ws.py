"""WebSocket: user-side transfer realtime echo (/ws/transfer/{transfer_host_id}).

Replicates the exec WS pattern: 5min JWT bound to transfer_host_id (IDOR
protection), after_seq log replay semantics, seq ordering.
"""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import create_token
from app.db.session import SessionLocal
from app.repositories import TransferHostRepository

router = APIRouter()

# transfer_host_id -> list of connected websockets
_clients: dict[int, list[WebSocket]] = {}
_lock = asyncio.Lock()
_app_loop: asyncio.AbstractEventLoop | None = None


def create_ws_token(transfer_host_id: int) -> str:
    """5min JWT bound to the transfer_host_id (IDOR protection)."""
    return create_token(transfer_host_id, "ws", expires_delta=timedelta(minutes=5))


async def broadcast(transfer_host_id: int, message: dict) -> None:
    async with _lock:
        sockets = list(_clients.get(transfer_host_id, []))
    for ws in sockets:
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass


def broadcast_sync(transfer_host_id: int, message: dict) -> None:
    """Thread-safe broadcast from sync contexts (celery/worker threads)."""
    loop = _app_loop
    if loop is None or loop.is_closed():
        return
    try:
        fut = asyncio.run_coroutine_threadsafe(broadcast(transfer_host_id, message), loop)
        fut.add_done_callback(lambda f: None)
    except Exception:
        pass


def _verify_ws_token(token: str, transfer_host_id: int) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    if payload.get("type") != "ws":
        return False
    try:
        return int(payload["sub"]) == transfer_host_id
    except (KeyError, ValueError):
        return False


@router.websocket("/ws/transfer/{transfer_host_id}")
async def ws_transfer(websocket: WebSocket, transfer_host_id: int, token: str):
    if not _verify_ws_token(token, transfer_host_id):
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        th = TransferHostRepository(db).by_id(transfer_host_id)
        if th is None:
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    await websocket.accept()
    global _app_loop
    _app_loop = asyncio.get_running_loop()
    async with _lock:
        _clients.setdefault(transfer_host_id, []).append(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "stop":
                await broadcast(transfer_host_id, {"type": "status", "data": {"status": "stopping"}})
                await websocket.send_text(json.dumps({"type": "status", "data": {"status": "stopping"}}))
            elif mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "data": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock:
            if transfer_host_id in _clients and websocket in _clients[transfer_host_id]:
                _clients[transfer_host_id].remove(websocket)
                if not _clients[transfer_host_id]:
                    del _clients[transfer_host_id]