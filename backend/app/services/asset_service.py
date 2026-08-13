"""Asset service: host groups, hosts, credentials (AES-GCM encrypted), connectivity."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.models import AssetGroup, Host, HostCredential
from app.repositories import CredentialRepository, GroupRepository, HostRepository
from app.schemas import asset as sch


# ---------------------------------------------------------------- groups


def group_tree(db: Session) -> list[dict]:
    groups = GroupRepository(db).all_tree()
    by_id: dict[int, dict] = {}
    for g in groups:
        by_id[g.id] = {**sch.GroupOut.model_validate(g).model_dump(), "children": []}
    roots: list[dict] = []
    for g in groups:
        item = by_id[g.id]
        if g.parent_id and g.parent_id in by_id:
            by_id[g.parent_id]["children"].append(item)
        else:
            roots.append(item)
    return roots


def create_group(db: Session, data: sch.GroupCreate) -> int:
    repo = GroupRepository(db)
    if data.parent_id and repo.get(data.parent_id) is None:
        raise BadRequestError("parent group not found")
    g = repo.add(AssetGroup(**data.model_dump()))
    db.flush()
    db.commit()
    return g.id


def update_group(db: Session, group_id: int, data: sch.GroupUpdate) -> None:
    repo = GroupRepository(db)
    g = repo.get(group_id)
    if g is None:
        raise NotFoundError("group not found")
    if data.parent_id is not None:
        if data.parent_id == group_id:
            raise BadRequestError("cannot set self as parent")
        g.parent_id = data.parent_id
    for f in ("name", "sort", "remark"):
        v = getattr(data, f)
        if v is not None:
            setattr(g, f, v)
    db.commit()


def delete_group(db: Session, group_id: int) -> None:
    repo = GroupRepository(db)
    if repo.get(group_id) is None:
        raise NotFoundError("group not found")
    if repo.children_count(group_id) > 0:
        raise ConflictError("group has children, delete them first")
    if repo.host_count(group_id) > 0:
        raise ConflictError("group has hosts, move them first")
    db.delete(repo.get(group_id))
    db.commit()


# ---------------------------------------------------------------- hosts


def _visible_group_filter(user, filters: dict) -> dict:
    """Enforce data permission: non-admin can only see their visible host groups.
    Default-deny: visible_group_ids empty -> no host data (US-03)."""
    if user.is_admin:
        return filters
    if "group_ids" not in filters:
        filters["group_ids"] = user.visible_group_ids
    else:
        filters["group_ids"] = [g for g in filters["group_ids"] if g in user.visible_group_ids]
    return filters


def list_hosts(db: Session, user, hostname: str | None, ip: str | None, os_type: str | None,
               group_id: int | None, env: str | None, tag: str | None, status: str | None,
               connector: str | None, page: int, size: int) -> dict:
    filters: dict[str, Any] = {
        "hostname": hostname, "ip": ip, "os_type": os_type, "env": env, "status": status,
        "connector": connector, "tag": tag,
    }
    if group_id:
        filters["group_id"] = group_id
    filters = _visible_group_filter(user, filters)
    rows, total = HostRepository(db).search(filters, page, size)
    return {
        "list": [sch.HostOut.model_validate(h).model_dump() for h in rows],
        "total": total, "page": page, "size": size,
    }


def _host_visible(user, host: Host) -> bool:
    if user.is_admin:
        return True
    return host.group_id in user.visible_group_ids


def get_host(db: Session, user, host_id: int) -> dict:
    repo = HostRepository(db)
    host = repo.get(host_id)
    if host is None:
        raise NotFoundError("host not found")
    if not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    data = sch.HostOut.model_validate(host).model_dump()
    cred = CredentialRepository(db).by_host(host_id)
    data["credential"] = None
    if cred:
        data["credential"] = {
            "id": cred.id, "type": cred.type, "username": cred.username,
            "secret_mask": mask_secret(cred.secret_enc), "key_mask": mask_secret(cred.key_enc),
            "key_version": cred.key_version,
        }
    return data


def create_host(db: Session, user, data: sch.HostCreate) -> int:
    if not user.is_admin and data.group_id not in user.visible_group_ids:
        raise ForbiddenError("no data permission for this host group")
    repo = HostRepository(db)
    if repo.by_ip(data.ip):
        raise ConflictError("ip already exists")
    host = Host(**data.model_dump(), created_by=user.id)
    repo.add(host)
    db.flush()
    db.commit()
    return host.id


def update_host(db: Session, user, host_id: int, data: sch.HostUpdate) -> None:
    repo = HostRepository(db)
    host = repo.get(host_id)
    if host is None:
        raise NotFoundError("host not found")
    if not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    for f in ("hostname", "os_type", "os_version", "group_id", "env", "tags", "connector", "remark"):
        v = getattr(data, f)
        if v is not None:
            setattr(host, f, v)
    db.commit()


def delete_host(db: Session, user, host_id: int) -> None:
    repo = HostRepository(db)
    host = repo.get(host_id)
    if host is None:
        raise NotFoundError("host not found")
    if not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    from app.db.models import ExecTask, ExecTaskHost, ScheduleTask
    from sqlalchemy import func, select

    task_refs = db.scalar(select(func.count()).select_from(ExecTaskHost).where(ExecTaskHost.host_id == host_id)) or 0
    sched_refs = db.scalar(select(func.count()).select_from(ScheduleTask).where(
        ScheduleTask.target_host_ids.cast("text").like(f"%{host_id}%"))
    ) or 0
    if task_refs or sched_refs:
        raise ConflictError("host referenced by tasks or schedules")
    db.delete(host)
    db.commit()


def import_hosts(db: Session, user, csv_bytes: bytes) -> dict:
    repo = HostRepository(db)
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    success = 0
    failed: list[dict] = []
    for idx, row in enumerate(reader, start=2):
        ip = (row.get("ip") or "").strip()
        hostname = (row.get("hostname") or "").strip()
        if not ip or not hostname:
            failed.append({"row": idx, "error": "ip and hostname required"})
            continue
        if repo.by_ip(ip):
            failed.append({"row": idx, "error": "ip already exists"})
            continue
        group_id = None
        gname = (row.get("group") or "").strip()
        if gname:
            group = db.query(AssetGroup).filter(AssetGroup.name == gname).first()
            if group:
                group_id = group.id
        host = Host(
            hostname=hostname, ip=ip,
            os_type=row.get("os_type") or "linux",
            os_version=row.get("os_version") or "",
            group_id=group_id,
            env=row.get("env") or "prod",
            tags={"label": row.get("tags")} if row.get("tags") else None,
            connector=row.get("connector") or "agent",
            remark=row.get("remark") or "",
            created_by=user.id,
        )
        repo.add(host)
        success += 1
    db.commit()
    return {"success": success, "failed": failed}


def export_hosts(db: Session, user) -> str:
    filters = _visible_group_filter(user, {})
    rows, _ = HostRepository(db).search(filters, 1, 100000)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["hostname", "ip", "os_type", "os_version", "env", "group", "status", "connector", "remark"])
    groups = {g.id: g.name for g in GroupRepository(db).all_tree()}
    for h in rows:
        writer.writerow([h.hostname, h.ip, h.os_type, h.os_version, h.env, groups.get(h.group_id, ""),
                         h.status, h.connector, h.remark])
    return buf.getvalue()


def host_stats(db: Session, user) -> dict:
    filters = _visible_group_filter(user, {})
    return HostRepository(db).stats(filters.get("group_ids"))


def connectivity_check(db: Session, user, host_id: int) -> dict:
    host = HostRepository(db).get(host_id)
    if host is None:
        raise NotFoundError("host not found")
    if not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    # MVP: agent heartbeat freshness decides connectivity; SSH fallback unsupported yet.
    from datetime import datetime, timedelta, timezone

    ok = False
    detail = "no agent"
    latency = 0
    if host.connector == "agent" and host.last_heartbeat_at:
        age = (datetime.now(timezone.utc) - host.last_heartbeat_at).total_seconds()
        if age <= 90:
            ok = True
            detail = f"agent online, heartbeat {int(age)}s ago"
        else:
            detail = f"agent stale, last heartbeat {int(age)}s ago"
    elif host.connector == "ssh":
        detail = "ssh connector check not implemented in MVP (degraded mode)"
    if ok:
        host.status = "online"
    else:
        host.status = "offline"
    db.commit()
    return {"ok": ok, "latency_ms": latency, "detail": detail}


# ---------------------------------------------------------------- credentials


def list_credentials(db: Session, user) -> list[dict]:
    repo = CredentialRepository(db)
    creds = repo.list_all()
    out = []
    hosts = {h.id: h for h in HostRepository(db).list_all()}
    for c in creds:
        host = hosts.get(c.host_id)
        if host and not _host_visible(user, host):
            continue
        out.append({
            "id": c.id, "host_id": c.host_id,
            "hostname": host.hostname if host else "",
            "ip": host.ip if host else "",
            "type": c.type, "username": c.username,
            "secret_mask": mask_secret(c.secret_enc),
            "key_version": c.key_version,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return out


def create_credential(db: Session, user, data: sch.CredentialCreate) -> int:
    host = HostRepository(db).get(data.host_id)
    if host is None:
        raise NotFoundError("host not found")
    if not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    repo = CredentialRepository(db)
    if repo.by_host(data.host_id):
        raise ConflictError("credential already exists for this host")
    if data.type == "password" and not data.secret:
        raise BadRequestError("secret required for password credential")
    if data.type == "key" and not data.key:
        raise BadRequestError("key required for key credential")
    cred = HostCredential(
        host_id=data.host_id,
        type=data.type,
        username=data.username,
        secret_enc=encrypt_secret(data.secret) if data.secret else None,
        key_enc=encrypt_secret(data.key) if data.key else None,
        key_version=1,
        updated_by=user.id,
    )
    repo.add(cred)
    db.flush()
    db.commit()
    return cred.id


def update_credential(db: Session, user, cred_id: int, data: sch.CredentialUpdate) -> None:
    repo = CredentialRepository(db)
    cred = repo.get(cred_id)
    if cred is None:
        raise NotFoundError("credential not found")
    host = HostRepository(db).get(cred.host_id)
    if host and not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    if data.type:
        cred.type = data.type
    if data.username:
        cred.username = data.username
    if data.secret:
        cred.secret_enc = encrypt_secret(data.secret)
    if data.key:
        cred.key_enc = encrypt_secret(data.key)
    cred.updated_by = user.id
    db.commit()


def delete_credential(db: Session, user, cred_id: int) -> None:
    repo = CredentialRepository(db)
    cred = repo.get(cred_id)
    if cred is None:
        raise NotFoundError("credential not found")
    host = HostRepository(db).get(cred.host_id)
    if host and not _host_visible(user, host):
        raise ForbiddenError("no data permission for this host")
    db.delete(cred)
    db.commit()


def options(db: Session, user) -> dict:
    groups = group_tree(db)
    filters = _visible_group_filter(user, {})
    rows, _ = HostRepository(db).search(filters, 1, 100000)
    return {
        "groups": groups,
        "hosts": [{"id": h.id, "hostname": h.hostname, "ip": h.ip, "group_id": h.group_id} for h in rows],
        "envs": ["dev", "test", "prod"],
        "os_types": ["linux", "windows"],
        "connectors": ["agent", "ssh"],
    }
