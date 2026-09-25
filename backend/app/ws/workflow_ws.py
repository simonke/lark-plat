"""P3-4b WebSocket gateway: workflow run realtime echo (/ws/workflow-runs/{run_id}).

Frozen contract: @架构 tuple **G** as revised (seq2986) + @需求 §27.2 §27.7③.
Token is a short-lived (5min) JWT bound to ``run_id`` (type=``ws``, IDOR guard,
mirrors exec/transfer); auth failure closes 4401, unknown run closes 4404.
S->C frames are **notifications**, not state carriers: ``{type,data,seq}`` with a
top-level per-run monotonic ``seq`` (reconnect de-dup); REST is authoritative.
The engine emits ``run`` (progress) and ``pong`` (ping reply); ``node`` is
**reserved** — clients ignore unknown types. C->S only ``ping``. Broadcasts are
**same-process** (engine host ①, the driver runs in the API process).
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

# run_id -> connected websockets / monotonic frame sequence
_clients: dict[int, list[WebSocket]] = {}
_seq: dict[int, int] = {}
_lock = asyncio.Lock()
_app_loop: asyncio.AbstractEventLoop | None = None


def create_ws_token(run_id: int) -> str:
    """5min JWT bound to run_id (IDOR protection; mirror exec/transfer)."""
    return create_token(run_id, "ws", timedelta(minutes=5))


def _next_seq(run_id: int) -> int:
    value = _seq.get(run_id, 0) + 1
    _seq[run_id] = value
    return value


async def broadcast(run_id: int, message: dict) -> None:
    async with _lock:
        sockets = list(_clients.get(run_id, []))
    if not sockets:
        return
    frame = dict(message)
    frame.setdefault("seq", _next_seq(run_id))
    for ws in sockets:
        try:
            await ws.send_text(json.dumps(frame))
        except Exception:  # noqa: BLE001
            pass


def broadcast_sync(run_id: int, message: dict) -> None:
    """Thread-safe broadcast from the in-process driver. Without a process event
    loop (offline tests) this is a no-op."""
    loop = _app_loop
    if loop is None or loop.is_closed():
        return
    try:
        fut = asyncio.run_coroutine_threadsafe(broadcast(run_id, message), loop)
        fut.add_done_callback(lambda f: None)
    except Exception:  # noqa: BLE001
        pass


def _verify_ws_token(token: str, run_id: int) -> bool:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    if payload.get("type") != "ws":
        return False
    try:
        return int(payload["sub"]) == run_id
    except (KeyError, ValueError):
        return False


@router.websocket("/ws/workflow-runs/{run_id}")
async def ws_workflow_run(websocket: WebSocket, run_id: int, token: str):
    # (a) contract fidelity (@架构 seq3012): accept the handshake BEFORE closing
    # with an application code; a pre-accept close is translated by uvicorn into
    # an HTTP 403 and the 4401/4404 close codes would be lost.
    await websocket.accept()
    if not _verify_ws_token(token, run_id):
        await websocket.close(code=4401)
        return
    db = SessionLocal()
    try:
        from app.db.models.workflow import WorkflowRun  # noqa: PLC0415

        if db.get(WorkflowRun, run_id) is None:
            await websocket.close(code=4404)
            return
    finally:
        db.close()

    global _app_loop
    _app_loop = asyncio.get_running_loop()
    async with _lock:
        _clients.setdefault(run_id, []).append(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
            if msg.get("type") == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong", "seq": _next_seq(run_id)})
                )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        async with _lock:
            if run_id in _clients and websocket in _clients[run_id]:
                _clients[run_id].remove(websocket)
                if not _clients[run_id]:
                    del _clients[run_id]
