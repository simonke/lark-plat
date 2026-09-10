"""WebSocket: monitor realtime alerts & metrics (/ws/monitor).

Token is a short-lived (5min) JWT bound to user_id.  S→C frames:
  hello{data:{subscribed,ids}}, alert{data:MonAlertOut},
  metric{data:{entity_id,metric_name,value,ts}}, pong.
C→S frames: subscribe{data:{scope,ids}}, ping.
Buffer 100 messages max; flush on reconnect.
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

router = APIRouter()

# user_id -> list of connected websockets
_clients: dict[int, list[WebSocket]] = {}
_lock = asyncio.Lock()
_app_loop: asyncio.AbstractEventLoop | None = None

# Per-connection subscription state
# ws -> {scope: "all"|"host"|"app", ids: set[str]}
_subs: dict[WebSocket, dict] = {}

# Ring buffer for reconnect flush (max 100 per user)
_buffer: dict[int, list[dict]] = {}
_BUFFER_MAX = 100


def create_ws_token(user_id: int) -> str:
    """5min JWT bound to the user_id."""
    return create_token(user_id, "ws", expires_delta=timedelta(minutes=5))


async def broadcast(user_id: int, message: dict) -> None:
    async with _lock:
        sockets = list(_clients.get(user_id, []))
        subs = dict(_subs)
    for ws in sockets:
        sub = subs.get(ws, {"scope": "all", "ids": set()})
        if not _matches_subscription(message, sub):
            continue
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            pass


def broadcast_sync(user_id: int, message: dict) -> None:
    """Thread-safe broadcast from sync contexts (celery/worker threads)."""
    loop = _app_loop
    if loop is None or loop.is_closed():
        return
    # Buffer for reconnect flush
    buf = _buffer.setdefault(user_id, [])
    buf.append(message)
    if len(buf) > _BUFFER_MAX:
        buf.pop(0)
    try:
        fut = asyncio.run_coroutine_threadsafe(broadcast(user_id, message), loop)
        fut.add_done_callback(lambda f: None)
    except Exception:
        pass


def _matches_subscription(message: dict, sub: dict) -> bool:
    """US-03: server-side scope filtering for WS messages."""
    scope = sub.get("scope", "all")
    if scope == "all":
        return True
    ids = sub.get("ids", set())
    if not ids:
        return True
    data = message.get("data") or {}
    entity = data.get("entity") or {}
    entity_id = str(entity.get("entity_id") or data.get("entity_id") or "")
    return entity_id in ids


def _verify_ws_token(token: str) -> int | None:
    """Verify WS JWT and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
    if payload.get("type") != "ws":
        return None
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        return None


@router.websocket("/ws/monitor")
async def ws_monitor(websocket: WebSocket, token: str):
    user_id = _verify_ws_token(token)
    if user_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    global _app_loop
    _app_loop = asyncio.get_running_loop()

    async with _lock:
        _clients.setdefault(user_id, []).append(websocket)
        _subs[websocket] = {"scope": "all", "ids": set()}

    # Send hello frame with current subscription
    await websocket.send_text(json.dumps({
        "type": "hello",
        "data": {"subscribed": True, "ids": []},
    }))

    # Flush buffered messages
    buf = _buffer.pop(user_id, [])
    for msg in buf:
        try:
            await websocket.send_text(json.dumps(msg))
        except Exception:
            break

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            if mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "data": {}}))
            elif mtype == "subscribe":
                data = msg.get("data") or {}
                scope = data.get("scope", "all")
                ids = set(str(i) for i in (data.get("ids") or []))
                async with _lock:
                    _subs[websocket] = {"scope": scope, "ids": ids}
                await websocket.send_text(json.dumps({
                    "type": "hello",
                    "data": {"subscribed": True, "ids": list(ids)},
                }))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        async with _lock:
            if user_id in _clients and websocket in _clients[user_id]:
                _clients[user_id].remove(websocket)
                if not _clients[user_id]:
                    del _clients[user_id]
            _subs.pop(websocket, None)
