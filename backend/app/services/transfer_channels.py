"""TransferChannel abstraction (architecture-phase23 §3 decision 1).

AgentChannel is the default and only implemented channel this batch; SshChannel
is an interface placeholder (SCP/sftp fallback deferred to P2-4). A target host
whose channel is unavailable is marked `degraded` (log explains why; not a hard
failure) per the requirements ruling.

Wire protocol (api-design-v3 §1 WS frame table, exec-style envelope):
  S->C file_send     {transfer_host_id, task_no, mode:push, file_item{path,size,sha256,chunk_size}, offset, target_path, overwrite, verify, limit_mbps}
  S->C file_chunk    {transfer_host_id, path, offset, bytes, crc32, data:<b64>}
  S->C file_verify   {transfer_host_id, path, sha256}
  S->C file_fetch    {transfer_host_id, task_no, mode:pull, path, target_path, offset, verify}
  C->S file_chunk_ack{transfer_host_id, offset, bytes, crc32}
  C->S file_chunk    {transfer_host_id, path, offset, bytes, crc32, data:<b64>}   (pull data, symmetric)
  C->S file_result   {transfer_host_id, status, sha256, error}
  S->C/C->S stop     {transfer_host_id}
"""

from __future__ import annotations

import base64
import logging
import os
import threading
import time
import zlib
from typing import Protocol

from app.db.session import SessionLocal
from app.repositories import FilePackageRepository, HostRepository, TransferHostRepository
from app.ws.agent_ws import dispatch_to_agent_sync

logger = logging.getLogger(__name__)


def chunk_interval_ms(chunk_size: int, limit_mbps: int | None) -> float:
    """D2: per-chunk pacing = chunk_size x 8 / (limit x 1MiB x 1MiB) x 1000 ms."""
    if not limit_mbps or limit_mbps <= 0:
        return 0.0
    bits = chunk_size * 8
    budget_bps = limit_mbps * 1024 * 1024
    return max(0.0, (bits / budget_bps) * 1000.0)


class TransferChannel(Protocol):
    """Channel contract: how one host moves bytes (push) or fetches them (pull)."""

    channel_kind: str

    def can_handle(self, db, host) -> bool: ...

    def push(self, db, task, host, item, offset: int, target_path: str, overwrite: int,
             verify: int, limit_mbps: int | None) -> bool: ...

    def fetch(self, db, task, host, path: str, target_path: str, offset: int, verify: int) -> bool: ...


class AgentChannel:
    """Default channel: pushes via WS frames to a live agent bound to the host.

    file_send starts a push; the file bytes are streamed as S->C file_chunk frames
    (daemon thread, D3 throttling between chunks); the agent acks at the cursor
    (file_chunk_ack) and, when verify is enabled, answers file_verify by
    computing sha256 and returning a terminal file_result. Pull (fetch) hands the
    source path to the agent and lets it stream file_chunk frames back.
    """

    channel_kind = "agent"

    def can_handle(self, db, host) -> bool:
        if host is None or not host.agent_id:
            return False
        from app.ws.agent_ws import agent_online

        return agent_online(host.agent_id)

    def push(self, db, task, host, item, offset: int, target_path: str, overwrite: int,
             verify: int, limit_mbps: int | None) -> bool:
        agent = self._proc_agent(db, host)
        if agent is None:
            return False
        frame = {
            "type": "file_send",
            "data": {
                "transfer_host_id": host.id,
                "task_no": task.task_no,
                "mode": "push",
                "file_item": {
                    "path": item.rel_path,
                    "size": item.size,
                    "sha256": item.sha256,
                    "chunk_size": item.chunk_size,
                },
                "offset": offset,
                "target_path": target_path,
                "overwrite": overwrite,
                "verify": verify,
                "limit_mbps": limit_mbps,
            },
        }
        if not dispatch_to_agent_sync(agent.agent_id, frame):
            return False
        self._stream_chunks_async(agent.agent_id, host, item, started_at=offset, limit_mbps=limit_mbps)
        return True

    def fetch(self, db, task, host, path: str, target_path: str, offset: int, verify: int) -> bool:
        agent = self._proc_agent(db, host)
        if agent is None:
            return False
        return dispatch_to_agent_sync(agent.agent_id, {
            "type": "file_fetch",
            "data": {
                "transfer_host_id": host.id,
                "task_no": task.task_no,
                "mode": "pull",
                "path": path,
                "target_path": target_path,
                "offset": offset,
                "verify": verify,
            },
        })

    @staticmethod
    def _proc_agent(db, host):
        """Resolve the live Host record (push/fetch receive the TransferHost row)."""
        if host is None or not host.host_id:
            return None
        agent = HostRepository(db).get(host.host_id)
        return agent if agent is not None and agent.agent_id else None

    @staticmethod
    def _stream_chunks_async(agent_id: str, host, item, started_at: int, limit_mbps: int | None) -> None:
        """Stream local package bytes as S->C file_chunk frames in a daemon thread.

        The cursor/ack flow lives in the agent WS loop (file_chunk_ack / file_result);
        this thread only writes frames and paces them per D3.
        """

        def _run() -> None:
            interval = chunk_interval_ms(item.chunk_size, limit_mbps) / 1000.0
            try:
                db = SessionLocal()
                try:
                    package = FilePackageRepository(db).get(item.package_id)
                finally:
                    db.close()
                if package is None:
                    return
                path = os.path.join(package.store_path, item.rel_path.replace("/", os.sep))
                if not os.path.isfile(path):
                    logger.error("transfer: source file missing %s", path)
                    db = SessionLocal()
                    try:
                        TransferHostRepository(db).update_status(host.id, "failed")
                        db.commit()
                    finally:
                        db.close()
                    return
                with open(path, "rb") as fh:
                    offset = started_at
                    fh.seek(offset)
                    while True:
                        data = fh.read(item.chunk_size)
                        if not data:
                            break
                        if not dispatch_to_agent_sync(agent_id, {
                                "type": "file_chunk",
                                "data": {
                                    "transfer_host_id": host.id,
                                    "path": item.rel_path,
                                    "offset": offset,
                                    "bytes": len(data),
                                    "crc32": zlib.crc32(data) & 0xFFFFFFFF,
                                    "data": base64.b64encode(data).decode(),
                                },
                        }):
                            return
                        offset += len(data)
                        if interval > 0:
                            time.sleep(interval)
                if item.sha256:
                    dispatch_to_agent_sync(host.agent_id, {
                        "type": "file_verify",
                        "data": {
                            "transfer_host_id": host.id,
                            "path": item.rel_path,
                            "sha256": item.sha256,
                        },
                    })
                logger.info("transfer: chunk stream done for host %s item %s", host.id, item.rel_path)
            except Exception:  # noqa: BLE001 - best-effort streaming
                logger.exception("transfer: chunk streaming failed for host %s", host.id)

        threading.Thread(target=_run, daemon=True).start()


class SshChannel:
    """SSH/SCP fallback channel - interface placeholder (deferred to P2-4).

    Satisfies the TransferChannel protocol shape (can_handle -> False) so the
    engine degrades cleanly instead of inventing a partial implementation.
    """

    channel_kind = "ssh"

    def can_handle(self, db, host) -> bool:
        return False

    def push(self, db, task, host, item, offset: int, target_path: str, overwrite: int,
             verify: int, limit_mbps: int | None) -> bool:
        return False

    def fetch(self, db, task, host, path: str, target_path: str, offset: int, verify: int) -> bool:
        return False


def resolve_agent_channel(db, host) -> TransferChannel | None:
    """Ordered channel candidates for a host (AgentChannel first); None -> degraded."""
    for channel in (AgentChannel(), SshChannel()):
        if channel.can_handle(db, host):
            return channel
    return None