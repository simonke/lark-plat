"""Terminal service: session lifecycle, sensitive-host approval gate, concurrency
limits (429), WS token binding, and AES-GCM encrypted recording with replay.

Contract (api-design §6 terminals):
  - POST /terminals -> create session; sensitive host requires approval (awaiting)
  - WS token is a 5-min JWT bound to the session_id (IDOR protection)
  - recording stored AES-GCM, replayed with independent terminal:replay auth + audit
  - retention 30d by default (config_rule terminal_retention_days)
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
)
from app.core.security import encrypt_secret
from app.db.models import ApprovalRequest, ConfigRule, Host, TerminalSession
from app.repositories import (
    ApprovalRepository,
    ConfigRuleRepository,
    HostRepository,
    TerminalRecordingRepository,
    TerminalSessionRepository,
)
from app import schemas


_NO_LOCK = threading.Lock()
_NO_COUNTER = 0


def _unique_no_component() -> str:
    """Snowflake-ish race-free sequence: pid + process-monotonic counter. No
    max(id)+1 DB read, so concurrent creators never collide on the number
    (session_no unique constraint retained as a backstop)."""
    global _NO_COUNTER
    with _NO_LOCK:
        _NO_COUNTER += 1
        seq = _NO_COUNTER
    return f"{os.getpid():x}-{seq:08x}"


def _session_no(db: Session) -> str:
    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    return f"TS-{prefix}-{_unique_no_component()}"


def _rules(db: Session) -> dict:
    repo = ConfigRuleRepository(db)
    out = {
        "user_limit": 1,
        "global_limit": 100,
        "idle_timeout_sec": 1800,
        "duration_limit_sec": 14400,
        "retention_days": 30,
    }
    for key, target in (
        ("terminal_user_concurrency_limit", "user_limit"),
        ("terminal_global_concurrency_limit", "global_limit"),
        ("terminal_idle_timeout_sec", "idle_timeout_sec"),
        ("terminal_duration_limit_sec", "duration_limit_sec"),
        ("terminal_retention_days", "retention_days"),
    ):
        rule = repo.by_key(key)
        val = (rule.rule_value or {}) if rule else {}
        if rule and val.get("value") is not None:
            out[target] = int(val["value"])
    return out


def _host_visible(user, host: Host) -> None:
    if host is None:
        raise NotFoundError("host not found")
    if not user.is_admin and host.group_id not in user.visible_group_ids:
        raise ForbiddenError(f"no data permission for host {host.id}")


def create_session(db: Session, user, data: schemas.TerminalCreate) -> dict:
    user.require_perm("terminal:create")
    host = HostRepository(db).get(data.host_id)
    _host_visible(user, host)

    rules = _rules(db)
    repo = TerminalSessionRepository(db)
    if repo.count_open_by_user(user.id) >= rules["user_limit"]:
        raise RateLimitError("user terminal session concurrency limit reached")
    if repo.count_open_global() >= rules["global_limit"]:
        raise RateLimitError("global terminal session concurrency limit reached")

    session = TerminalSession(
        session_no=_session_no(db),
        host_id=host.id,
        user_id=user.id,
        status="open",
        sensitive=1 if host.sensitivity_level == "sensitive" else 0,
        started_at=datetime.now(timezone.utc),
    )
    repo.add(session)
    db.flush()

    approval_id = None
    status = "open"
    if host.sensitivity_level == "sensitive":
        approval = ApprovalRequest(
            request_no=_approval_no(db),
            biz_type="terminal",
            biz_id=session.id,
            title=f"Web终端审批：{host.hostname}({host.ip})",
            reason="敏感主机访问需审批",
            requester_id=user.id,
            sensitive_hit="sensitive host access",
            status="pending",
        )
        ApprovalRepository(db).add(approval)
        db.flush()
        approval_id = approval.id
        session.approval_id = approval.id
        session.status = "awaiting_approval"
        status = "awaiting_approval"

    db.commit()
    return {
        "id": session.id,
        "session_no": session.session_no,
        "host_id": session.host_id,
        "status": status,
        "sensitive": session.sensitive,
        "approval_id": approval_id,
        "ws_token": None,
    }


def _approval_no(db: Session) -> str:
    from datetime import date

    prefix = date.today().strftime("%Y%m%d")
    return f"AP-{prefix}-{_unique_no_component()}"


def _require_visible_session(db: Session, user, session_id: int) -> TerminalSession:
    session = TerminalSessionRepository(db).get(session_id)
    if session is None:
        raise NotFoundError("terminal session not found")
    if not user.is_admin and session.user_id != user.id:
        host = HostRepository(db).get(session.host_id)
        if host is None or host.group_id not in user.visible_group_ids:
            raise ForbiddenError("no permission to view this terminal session")
    return session


def get_session(db: Session, user, session_id: int) -> dict:
    user.require_perm("terminal:view")
    session = _require_visible_session(db, user, session_id)
    return _session_out(session)


def _session_out(s: TerminalSession) -> dict:
    return {
        "id": s.id, "session_no": s.session_no, "host_id": s.host_id, "user_id": s.user_id,
        "status": s.status, "close_reason": s.close_reason, "sensitive": s.sensitive,
        "approval_id": s.approval_id, "version": s.version,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
        "duration_sec": s.duration_sec, "bytes_out": s.bytes_out, "bytes_in": s.bytes_in,
    }


def list_sessions(db: Session, user, status: str | None, page: int, size: int) -> dict:
    user.require_perm("terminal:list")
    filters = {"status": status}
    if not user.is_admin:
        filters["user_id"] = user.id
    rows, total = TerminalSessionRepository(db).search(filters, page, size)
    return {"list": [_session_out(r) for r in rows], "total": total, "page": page, "size": size}


def issue_token(db: Session, user, session_id: int) -> dict:
    user.require_perm("terminal:view")
    session = _require_visible_session(db, user, session_id)
    if session.status not in ("open",):
        raise BadRequestError("terminal session is not open")
    from app.ws.terminal_ws import create_ws_token

    return {
        "session_id": session.id,
        "session_no": session.session_no,
        "ws_token": create_ws_token(session.id),
        "expires_in": 300,
    }


def close_session(db: Session, user, session_id: int) -> dict:
    user.require_perm("terminal:close")
    session = _require_visible_session(db, user, session_id)
    repo = TerminalSessionRepository(db)
    if session.status != "open":
        if session.status == "awaiting_approval":
            # cancel the linked pending approval so it does not linger
            if session.approval_id:
                approval = ApprovalRepository(db).get(session.approval_id)
                if approval is not None and approval.status == "pending":
                    ApprovalRepository(db).optimistic_update(
                        approval.id, "pending", "canceled", approval.version
                    )
            session.status = "closed"
            session.close_reason = "canceled_before_approval"
            session.finished_at = datetime.now(timezone.utc)
            db.commit()
            return {"id": session.id, "status": "closed"}
        raise BadRequestError("terminal session already closed")
    if not repo.optimistic_close(session.id, session.version):
        raise BadRequestError("terminal session state changed concurrently")
    session.version += 1
    session.status = "closed"
    session.close_reason = "manual"
    session.finished_at = datetime.now(timezone.utc)
    session.duration_sec = int(
        (session.finished_at - session.started_at).total_seconds()
        if session.started_at else 0
    )
    db.commit()
    return {"id": session.id, "status": "closed"}


def activate_on_approval(db: Session, approval: ApprovalRequest) -> None:
    """Called when a terminal-type approval is approved: open the session.

    started_at is reset at activation so duration/idle accounting starts from
    actual operation time (not the pre-approval wait) per §6.5 semantics.
    """
    if approval.biz_type != "terminal":
        return
    session = TerminalSessionRepository(db).get(approval.biz_id)
    if session is None or session.status != "awaiting_approval":
        return
    session.status = "open"
    session.started_at = datetime.now(timezone.utc)
    db.commit()


def close_on_cancel(db: Session, approval: ApprovalRequest) -> None:
    """Called when a terminal-type approval is canceled: close the awaiting
    session so it cannot later be activated and the concurrency slot frees."""
    if approval.biz_type != "terminal":
        return
    session = TerminalSessionRepository(db).get(approval.biz_id)
    if session is None or session.status != "awaiting_approval":
        return
    session.status = "closed"
    session.close_reason = "canceled_before_approval"
    session.finished_at = datetime.now(timezone.utc)
    db.commit()


def replay_recording(db: Session, user, session_id: int, after_offset: int, size: int) -> dict:
    """Replay recording with independent terminal:replay auth + audit. Expired/over
    retention sessions return 404 (data purged)."""
    user.require_perm("terminal:replay")
    session = _require_visible_session(db, user, session_id)
    repo = TerminalRecordingRepository(db)

    rules = _rules(db)
    retention = timedelta(days=rules["retention_days"])
    created = session.started_at or session.created_at
    if created is None or datetime.now(timezone.utc) - created > retention:
        raise NotFoundError("recording expired or purged")

    chunks = repo.after_offset(session_id, after_offset, size)
    max_offset = repo.max_offset(session_id)
    out = []
    for c in chunks:
        try:
            plain = _decrypt_chunk(c.data_enc)
        except Exception:
            plain = ""
        out.append({"offset": c.offset, "data": plain,
                    "created_at": c.created_at.isoformat() if c.created_at else None})
    return {
        "session_id": session_id,
        "after_offset": after_offset,
        "size": len(chunks),
        "has_more": max_offset > after_offset and len(chunks) == size,
        "chunks": out,
    }


def _decrypt_chunk(data_enc: str) -> str:
    from app.core.security import decrypt_secret

    return decrypt_secret(data_enc)


_REC_LOCK_GUARD = threading.Lock()
_REC_LOCKS: dict[int, threading.Lock] = {}


def _rec_lock(session_id: int) -> threading.Lock:
    with _REC_LOCK_GUARD:
        lock = _REC_LOCKS.get(session_id)
        if lock is None:
            lock = threading.Lock()
            _REC_LOCKS[session_id] = lock
        return lock


def record_output(db: Session, session: TerminalSession, output: str) -> None:
    """Append terminal output to the encrypted recording and update byte counters.

    Serial single-writer: offset assignment is serialized per-session so concurrent
    writers never produce the same offset (UniqueConstraint(session_id, offset))."""
    if not output:
        return
    lock = _rec_lock(session.id)
    with lock:
        repo = TerminalRecordingRepository(db)
        offset = repo.max_offset(session.id) + 1
        repo.append(session.id, offset, encrypt_secret(output))
        session.bytes_out += len(output.encode("utf-8", "replace"))


def mark_idle_timeout(db: Session, session: TerminalSession) -> None:
    if session.status != "open":
        return
    _finalize(db, session, "idle_timeout")


def mark_duration_limit(db: Session, session: TerminalSession) -> None:
    if session.status != "open":
        return
    _finalize(db, session, "duration_limit")


def _finalize(db: Session, session: TerminalSession, reason: str) -> None:
    repo = TerminalSessionRepository(db)
    if not repo.optimistic_close(session.id, session.version):
        return
    session.version += 1
    session.status = "closed"
    session.close_reason = reason
    session.finished_at = datetime.now(timezone.utc)
    session.duration_sec = int(
        (session.finished_at - session.started_at).total_seconds()
        if session.started_at else 0
    )
    db.commit()
