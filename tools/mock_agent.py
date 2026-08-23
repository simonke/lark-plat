#!/usr/bin/env python3
"""MockAgent - lark-plat agent-chain test fixture (api-design §12 client side).

Connects to /api/v1/agent/ws and exercises:
  hello -> hello_ack
  heartbeat(<=30s) -> heartbeat_ack          (host flips online when bound)
  ping -> pong                                (server-initiated probes)
  exec -> exec_log(seq ascending) + exec_result ; stop -> terminates job

Auth (backend/app/ws/agent_ws.py MVP rules):
  host bound to agent_id : token = sha256(f"{agent_id}:{SECRET_KEY}")[:32]
  unbound agent_id       : token = SECRET_KEY (bootstrap)
  On close 4401 the other candidate is tried automatically.

Usage:
  python tools/mock_agent.py                          # 6 heartbeats @10s then exit
  python tools/mock_agent.py --interval 3 --count 20 --exec-demo --verbose
  python tools/mock_agent.py --hold-timeout           # stop beating, hold >90s, close

Dependency: websockets (already present in backend/.venv).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

import websockets

DEFAULT_SERVER = "ws://127.0.0.1:8000"
WS_PATH = "/api/v1/agent/ws"


def load_secret_key(env_path: Path) -> str:
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip()
    print(f"[MOCK] WARN secret key not found at {env_path}")
    return ""


def derived_token(agent_id: str, secret: str) -> str:
    return hashlib.sha256(f"{agent_id}:{secret}".encode()).hexdigest()[:32]


class MockAgent:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.secret = ""
        self.seq = 0
        self.job: asyncio.Task | None = None

    def log(self, msg: str) -> None:
        if self.args.verbose or msg.startswith("[MOCK]"):
            print(msg, flush=True)

    async def connect(self) -> websockets.ClientConnection:
        uri = f"{self.args.server}{WS_PATH}?agent_id={self.args.agent_id}&token={{token}}"
        candidates: list[tuple[str, str]] = []
        if self.args.token:
            candidates.append(("explicit", self.args.token))
        else:
            candidates.append(("derived", derived_token(self.args.agent_id, self.secret)))
            candidates.append(("bootstrap", self.secret))
        last_err = "no attempt"
        for mode, token in candidates:
            try:
                ws = await websockets.connect(
                    uri.format(token=token),
                    additional_headers={"X-Agent-Token": token},
                    open_timeout=5,
                )
                self.log(f"[MOCK] connected agent_id={self.args.agent_id} auth_mode={mode}")
                return ws
            except Exception as exc:  # noqa: BLE001
                last_err = f"{mode}: {exc}"
                self.log(f"[MOCK] connect failed ({last_err})")
        raise SystemExit(f"[MOCK] unable to connect ({last_err})")

    async def send(self, ws, frame: dict) -> None:
        await ws.send(json.dumps(frame))

    async def fake_exec(self, ws, data: dict) -> None:
        task_host_id = int(data.get("task_host_id") or self.args.task_host_id)
        cmd = data.get("command") or data.get("content") or "echo mock"
        self.log(f"[MOCK] exec received task_host_id={task_host_id} command={cmd!r}")
        try:
            for i in range(1, 4):
                await asyncio.sleep(0.5)
                self.seq += 1
                await self.send(ws, {"type": "exec_log", "data": {"items": [{
                    "task_host_id": task_host_id, "seq": self.seq,
                    "level": "info", "content": f"mock output line {self.seq} for {cmd}",
                }]}})
                self.log(f"[MOCK] exec_log seq={self.seq} sent")
            await self.send(ws, {"type": "exec_result", "data": {
                "task_host_id": task_host_id, "status": "success", "exit_code": 0}})
            self.log("[MOCK] exec_result success sent")
        except asyncio.CancelledError:
            self.seq += 1
            await self.send(ws, {"type": "exec_log", "data": {"items": [{
                "task_host_id": task_host_id, "seq": self.seq,
                "level": "warn", "content": "mock job stopped by stop frame",
            }]}})
            await self.send(ws, {"type": "exec_result", "data": {
                "task_host_id": task_host_id, "status": "stopped"}})
            self.log("[MOCK] exec_result stopped sent")

    async def receiver(self, ws) -> None:
        async for raw in ws:
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[MOCK] bad frame skipped: {exc}", flush=True)
                continue
            mtype = frame.get("type")
            if mtype in ("hello_ack", "heartbeat_ack"):
                self.log(f"[MOCK] <- {mtype} {frame.get('data', '')}")
            elif mtype == "ping":
                await self.send(ws, {"type": "pong"})
                self.log("[MOCK] ping -> pong")
            elif mtype == "heartbeat":
                await self.send(ws, {"type": "pong"})
            elif mtype == "exec":
                if self.args.exec_demo and not (self.job and not self.job.done()):
                    self.job = asyncio.create_task(self.fake_exec(ws, frame.get("data") or {}))
            elif mtype == "stop":
                if self.job:
                    self.job.cancel()
            else:
                self.log(f"[MOCK] <- {mtype}")

    async def run(self) -> int:
        env_path = Path(self.args.env)
        self.secret = load_secret_key(env_path)
        ws = await self.connect()
        hello_seen = False
        try:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            hello_seen = first.get("type") == "hello_ack"
            self.log(f"[MOCK] <- {first.get('type')} (hello_ack expected)")
            if not hello_seen:
                print("[MOCK] FAIL: first server frame is not hello_ack")
                return 2
            await self.send(ws, {"type": "hello", "data": {
                "hostname": self.args.hostname, "ip": self.args.ip,
                "os_type": "linux", "os_version": "mock", "agent_version": "mock-1.0"}})

            recv_task = asyncio.create_task(self.receiver(ws))
            beat = {"os_type": "linux", "os_version": "mock", "agent_version": "mock-1.0"}
            i = 0
            while self.args.count <= 0 or i < self.args.count:
                i += 1
                await self.send(ws, {"type": "heartbeat", "data": dict(beat)})
                label = f"#{i}" if self.args.count > 0 else f"#{i} (infinite)"
                self.log(f"[MOCK] heartbeat {label}/{self.args.count or 'inf'} sent (interval={self.args.interval}s)")
                deadline = asyncio.get_event_loop().time() + self.args.interval
                while asyncio.get_event_loop().time() < deadline:
                    if recv_task.done():
                        break
                    await asyncio.sleep(0.05)
            if self.args.hold_timeout:
                wait = self.args.hold_timeout_wait_sec
                self.log(f"[MOCK] holding connection silent {wait}s (>90s offline rule) ...")
                await asyncio.sleep(wait)
            recv_task.cancel()
            await ws.close()
            self.log("[MOCK] connection closed gracefully")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"[MOCK] FAIL: {exc}")
            return 1


def main() -> int:
    here = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="lark-plat MockAgent fixture")
    p.add_argument("--server", default=os.environ.get("MOCK_AGENT_SERVER", DEFAULT_SERVER))
    p.add_argument("--agent-id", default="mock-agent-1")
    p.add_argument("--hostname", default="mock-agent-host",
                   help="hostname reported in hello frame (§12) used for auto-binding")
    p.add_argument("--ip", default="10.254.0.99",
                   help="ip reported in hello frame (§12) used for auto-binding")
    p.add_argument("--token", default="", help="explicit token; default auto-derive/bootstrap from SECRET_KEY")
    p.add_argument("--env", default=str(here / "backend" / ".env"))
    p.add_argument("--interval", type=int, default=10, help="heartbeat interval seconds (must be <=30)")
    p.add_argument("--count", type=int, default=6, help="heartbeats to send (0 = until Ctrl-C)")
    p.add_argument("--hold-timeout", action="store_true", help="after heartbeats, hold silent >90s then close")
    p.add_argument("--hold-timeout-wait-sec", type=int, default=95)
    p.add_argument("--exec-demo", action="store_true", help="answer exec frames with exec_log/exec_result")
    p.add_argument("--task-host-id", type=int, default=1)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    if args.interval > 30:
        p.error("--interval must be <= 30s (server marks stale after 90s of silence)")
    return asyncio.run(MockAgent(args).run())


if __name__ == "__main__":
    sys.exit(main())
