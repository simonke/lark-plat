"""Transfer service: package upload, task state machine, stop/retry,
whitelist enforcement, log pagination, WS token.

Per-host lifecycle: pending -> (pulling|transferring) -> verifying -> success |
failed | verify_failed | degraded | canceled. Task aggregation: success when every
host is success (degraded hosts are not counted as hard failure per the
requirements ruling); partial when some succeeded; failed when none succeeded.
"""

from __future__ import annotations

import hashlib
import logging
import posixpath
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.db.models import FileItem, FilePackage, Host, TransferHost, TransferTask
from app.repositories import (
    ConfigRuleRepository,
    FileItemRepository,
    FilePackageRepository,
    HostRepository,
    TransferHostRepository,
    TransferLogRepository,
    TransferTaskRepository,
)
from app.services import transfer_channels
from app.tasks.transfer_tasks import transfer_dispatch
from app.ws.transfer_ws import broadcast_sync

logger = logging.getLogger(__name__)

DEFAULT_PULL_WHITELIST = ["/var/lib/lark-agent/outbox"]
DEFAULT_CHUNK_SIZE = 1048576


# =============================================================== helpers


def _feature_enabled(db: Session) -> bool:
    """feature.transfer config_rule namespace: disabled only when explicitly turned off."""
    rule = ConfigRuleRepository(db).by_key("feature.transfer")
    if rule and (rule.rule_value or {}).get("enabled") == 0:
        return False
    return True


def _task_no(db: Session) -> str:
    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    n = db.execute(text("SELECT nextval('seq_transfer_no')")).scalar()
    return f"TF-{prefix}-{int(n):03d}"


def _chunk_size(db: Session) -> int:
    rule = ConfigRuleRepository(db).by_key("transfer.chunk_size")
    val = int((rule.rule_value or {}).get("chunk_size", DEFAULT_CHUNK_SIZE)) if rule else DEFAULT_CHUNK_SIZE
    return val if val > 0 else DEFAULT_CHUNK_SIZE


def _pull_whitelist(db: Session) -> list[str]:
    rule = ConfigRuleRepository(db).by_key("transfer.pull_whitelist")
    if rule:
        val = (rule.rule_value or {}).get("paths") or (rule.rule_value or {}).get("whitelist")
        if isinstance(val, list):
            return [str(p) for p in val]
    return list(DEFAULT_PULL_WHITELIST)


def path_within_whitelist(path: str, whitelist: list[str]) -> bool:
    """Lexical containment check for pull sources (D1).

    Server-side defence-in-depth; the agent performs its own prefix check plus
    '.'/'..'/symlink-escape rejection ('dropped + error' per D1).
    """
    if not path or not path.startswith("/"):
        return False
    p = posixpath.normpath(path)
    if p == "/" or any(seg in ("..", ".") for seg in p.split("/")):
        return False
    for prefix in whitelist or []:
        base = posixpath.normpath(prefix)
        if not base.startswith("/"):
            continue
        if p == base or p.startswith(base.rstrip("/") + "/"):
            return True
    return False


def _safe_rel_path(name: str) -> str:
    """Normalize an uploaded filename to a store-safe relative path."""
    n = (name or "file").replace("\\", "/").lstrip("/")
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or not parts:
        raise BadRequestError("invalid file path in upload")
    return "/".join(parts)


# =============================================================== packages


def create_package(db: Session, user, files: list, name: str = "") -> dict:
    user.require_perm("transfer:package:add")
    if not _feature_enabled(db):
        raise BadRequestError("transfer feature disabled")
    if not files:
        raise BadRequestError("files[] required")
    store_root = Path(settings.transfer_store_dir)
    pkg_dir = store_root / uuid.uuid4().hex
    pkg_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    total = 0
    for f in files:
        rel = _safe_rel_path(f.filename or (getattr(f, "name", "") or "file"))
        data = f.file.read() if hasattr(f, "file") else (f.read() if hasattr(f, "read") else b"")
        digest = hashlib.sha256(data).hexdigest()
        dest = pkg_dir.joinpath(*rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        items.append({"path": rel, "size": len(data), "sha256": digest})
        total += len(data)
    if not items:
        raise BadRequestError("no usable files in upload")
    pkg = FilePackage(
        name=name or f"pkg-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        file_count=len(items),
        total_size=total,
        store_path=str(pkg_dir),
        created_by=user.id,
    )
    FilePackageRepository(db).add(pkg)
    db.flush()
    cs = _chunk_size(db)
    fixture_repo = FileItemRepository(db)
    for it in items:
        fixture_repo.add(FileItem(
            package_id=pkg.id, rel_path=it["path"], size=it["size"],
            sha256=it["sha256"], chunk_size=cs,
        ))
    db.commit()
    return {"package_id": pkg.id, "items": items}


def list_packages(db: Session, user, name: str | None, start, end, page: int, size: int) -> dict:
    user.require_perm("transfer:package:list")
    rows, total = FilePackageRepository(db).search(name, start, end, page, size)
    def _out(p: FilePackage) -> dict:
        return {
            "id": p.id, "name": p.name, "file_count": p.file_count,
            "total_size": p.total_size, "created_by": p.created_by,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
    return {"list": [_out(p) for p in rows], "total": total, "page": page, "size": size}


def get_package(db: Session, user, package_id: int) -> dict:
    user.require_perm("transfer:package:list")
    pkg = FilePackageRepository(db).get(package_id)
    if pkg is None:
        raise NotFoundError("package not found")
    def _item(it: FileItem) -> dict:
        return {"path": it.rel_path, "size": it.size, "sha256": it.sha256}
    return {
        "id": pkg.id, "name": pkg.name, "file_count": pkg.file_count,
        "total_size": pkg.total_size, "created_by": pkg.created_by,
        "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
        "items": [_item(it) for it in FileItemRepository(db).by_package(package_id)],
    }


def delete_package(db: Session, user, package_id: int) -> dict:
    user.require_perm("transfer:package:del")
    pkg = FilePackageRepository(db).get(package_id)
    if pkg is None:
        raise NotFoundError("package not found")
    if FilePackageRepository(db).referenced_count(package_id) > 0:
        raise ConflictError("package referenced by a running transfer task")
    pkg_path = Path(pkg.store_path)
    shutil.rmtree(pkg_path, ignore_errors=True)
    db.delete(pkg)
    db.commit()
    return {"id": package_id, "deleted": True}


# =============================================================== tasks


def create_task(db: Session, user, data) -> dict:
    user.require_perm("transfer:task:run")
    if not _feature_enabled(db):
        raise BadRequestError("transfer feature disabled")
    host_repo = HostRepository(db)
    hosts: dict[int, Host] = {}
    for hid in data.host_ids:
        host = host_repo.get(hid)
        if host is None:
            raise NotFoundError(f"host {hid} not found")
        if not user.is_admin and host.group_id not in user.visible_group_ids:
            raise ForbiddenError(f"no data permission for host {hid}")
        hosts[hid] = host

    if data.mode not in ("push", "pull"):
        raise BadRequestError("invalid mode (push/pull)")
    ctor: dict = {"mode": data.mode, "package_id": None, "source_host_id": None, "source_host_path": None}
    if data.mode == "push":
        if data.package_id is None:
            raise BadRequestError("package_id required for push mode")
        pkg = FilePackageRepository(db).get(data.package_id)
        if pkg is None:
            raise NotFoundError("package not found")
        if not FileItemRepository(db).by_package(pkg.id):
            raise BadRequestError("package has no files")
        ctor["package_id"] = pkg.id
    else:
        if not data.source_host_path:
            raise BadRequestError("source_host_path required for pull mode")
        if not path_within_whitelist(data.source_host_path, _pull_whitelist(db)):
            raise BadRequestError("source_host_path outside pull whitelist")
        ctor["source_host_path"] = data.source_host_path
        ctor["source_host_id"] = data.source_host_id

    task = TransferTask(
        task_no=_task_no(db),
        target_path=data.target_path,
        host_ids={"ids": data.host_ids},
        overwrite=data.overwrite,
        verify=data.verify,
        limit_mbps=data.limit_mbps,
        status="processing",
        created_by=user.id,
        **ctor,
    )
    task_repo = TransferTaskRepository(db)
    task_repo.add(task)
    db.flush()
    th_repo = TransferHostRepository(db)
    for hid in data.host_ids:
        h = hosts[hid]
        th_repo.add(TransferHost(
            transfer_task_id=task.id, host_id=h.id, hostname=h.hostname, ip=h.ip,
            channel="agent", status="pending",
        ))
    db.commit()
    _kick_off_transfer(db, task.id)
    return {"id": task.id, "task_no": task.task_no, "status": "processing",
            "pending": len(data.host_ids)}


def _kick_off_transfer(db: Session, task_id: int) -> None:
    """Dispatch a transfer task in-process when a live agent is bound in THIS
    process (celery worker has an empty agent registry), else via celery, else
    in-process degraded fallback (mirrors exec dispatch semantics)."""
    from app.ws.agent_ws import task_has_inprocess_transfer

    if task_has_inprocess_transfer(db, task_id):
        transfer_dispatch(task_id)
        return
    try:
        transfer_dispatch.delay(task_id)
    except Exception:
        transfer_dispatch(task_id)


def list_tasks(db: Session, user, mode: str | None, status: str | None, start, end,
               page: int, size: int) -> dict:
    user.require_perm("transfer:task:list")
    filters = {"mode": mode, "status": status, "start": start, "end": end}
    if not user.is_admin:
        filters["created_by"] = user.id
    rows, total = TransferTaskRepository(db).search(filters, page, size)
    return {"list": [_task_out(t) for t in rows], "total": total, "page": page, "size": size}


def _task_out(t: TransferTask) -> dict:
    return {
        "id": t.id, "task_no": t.task_no, "mode": t.mode, "package_id": t.package_id,
        "source_host_id": t.source_host_id, "source_host_path": t.source_host_path,
        "target_path": t.target_path, "host_ids": t.host_ids, "overwrite": t.overwrite,
        "verify": t.verify, "limit_mbps": t.limit_mbps, "status": t.status,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "started_at": t.started_at.isoformat() if t.started_at else None,
        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
    }


def get_task(db: Session, user, task_id: int) -> dict:
    user.require_perm("transfer:task:list")
    task = TransferTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    data = _task_out(task)
    data["hosts"] = [_host_out(h) for h in TransferHostRepository(db).by_task(task_id)]
    data["stats"] = task_stats_internal(db, task_id)
    return data


def _host_out(h: TransferHost) -> dict:
    return {
        "id": h.id, "host_id": h.host_id, "hostname": h.hostname, "ip": h.ip,
        "channel": h.channel, "status": h.status, "current_offset": h.current_offset,
        "verify_sha256": h.verify_sha256, "error": h.error,
        "started_at": h.started_at.isoformat() if h.started_at else None,
        "finished_at": h.finished_at.isoformat() if h.finished_at else None,
    }


def _stats(stats_map: dict) -> dict:
    def g(k: str) -> int:
        return stats_map.get(k, 0)

    return {
        "total": sum(stats_map.values()),
        "pending": g("pending"),
        "transferring": g("transferring") + g("pulling"),
        "verifying": g("verifying"),
        "verify_failed": g("verify_failed"),
        "success": g("success"),
        "failed": g("failed") + g("canceled") + g("degraded"),
    }


def task_stats_internal(db: Session, task_id: int) -> dict:
    return _stats(TransferHostRepository(db).stats(task_id))


def task_stats(db: Session, user, task_id: int) -> dict:
    user.require_perm("transfer:task:list")
    task = TransferTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    return task_stats_internal(db, task_id)


def get_logs(db: Session, user, task_id: int, transfer_host_id: int, after_seq: int, size: int) -> dict:
    user.require_perm("transfer:task:log")
    task = TransferTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    th_repo = TransferHostRepository(db)
    th = th_repo.by_id(transfer_host_id)
    if th is None or th.transfer_task_id != task_id:
        raise NotFoundError("task host not found")
    rows, _ = TransferLogRepository(db).after_seq(transfer_host_id, after_seq, size)
    next_seq = after_seq + len(rows)
    return {"list": [{"seq": r.seq, "level": r.level, "content": r.content,
                      "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows],
            "next_seq": next_seq}


def ws_token(db: Session, user, task_id: int, transfer_host_id: int) -> dict:
    user.require_perm("transfer:task:log")
    task = TransferTaskRepository(db).get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to view this task")
    th_repo = TransferHostRepository(db)
    th = th_repo.by_id(transfer_host_id)
    if th is None or th.transfer_task_id != task_id:
        raise NotFoundError("task host not found")
    from app.ws.transfer_ws import create_ws_token

    return {"token": create_ws_token(transfer_host_id)}


def stop_task(db: Session, user, task_id: int) -> dict:
    user.require_perm("transfer:task:stop")
    repo = TransferTaskRepository(db)
    task = repo.get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to stop this task")
    if task.status != "processing":
        raise BadRequestError("task not processing")
    if not repo.optimistic_update(task.id, "processing", "canceled", task.version):
        raise ConflictError("task state changed concurrently")
    task.version += 1
    task.finished_at = datetime.now(timezone.utc)
    th_repo = TransferHostRepository(db)
    for th in th_repo.by_task(task_id):
        if th.status in ("pending", "pulling", "transferring", "verifying"):
            was_active = th.status in ("pulling", "transferring", "verifying")
            th_repo.update_status(th.id, "canceled", finished_at=datetime.now(timezone.utc))
            if was_active:
                _send_stop(db, th)
    db.commit()
    logger.info("transfer: task %s stopped by %s", task_id, user.username)
    return {"id": task.id, "status": "canceled"}


def _send_stop(db: Session, th: TransferHost) -> None:
    """Best-effort interrupt of a live agent transfer - must not affect the state machine."""
    host = HostRepository(db).get(th.host_id) if th.host_id else None
    if host is None or not host.agent_id:
        return
    try:
        from app.ws.agent_ws import dispatch_to_agent_sync

        dispatch_to_agent_sync(host.agent_id, {"type": "stop", "data": {"transfer_host_id": th.id}})
    except Exception:  # noqa: BLE001 - best-effort interrupt
        logger.warning("transfer: stop dispatch failed for agent %s", host.agent_id)


def retry_host(db: Session, user, task_id: int, transfer_host_id: int) -> dict:
    user.require_perm("transfer:task:retry")
    task_repo = TransferTaskRepository(db)
    task = task_repo.get(task_id)
    if task is None:
        raise NotFoundError("task not found")
    if not user.is_admin and task.created_by != user.id:
        raise ForbiddenError("no permission to retry this task")
    th_repo = TransferHostRepository(db)
    th = th_repo.by_id(transfer_host_id)
    if th is None or th.transfer_task_id != task_id:
        raise NotFoundError("task host not found")
    if th.status not in ("failed", "verify_failed", "degraded", "canceled"):
        raise BadRequestError("host not retryable")

    # reopen the task (terminal task -> processing) and reset only this host
    if task.status != "processing":
        if not task_repo.optimistic_update(task.id, task.status, "processing", task.version):
            raise ConflictError("task state changed concurrently")
        task.version += 1
        task.finished_at = None
    th_repo.update_status(th.id, "pending",
                          error=None, verify_sha256=None, finished_at=None)
    db.commit()
    _kick_off_transfer(db, task_id)
    broadcast_sync(th.id, {"type": "status", "data": {"status": "pending", "retry": True}})
    return {"id": transfer_host_id, "status": "pending"}