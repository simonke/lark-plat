"""AIOps service surface (P4 E1/E2/E3/E7).

Gate order is **feature first** (seq3212 #2): every public function calls
``require_feature(db, "<flag>")`` then ``user.require_perm(...)``. US-03 (ADR#3)
is applied by pushing a `ScopeFilter` into the retrieval layer (never a
post-filter); `ai_action` is append-only.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import AI_ACTION_DECISIONS, AiAction, OpsEvent
from app.services.ai_gate import require_feature
from app.services.ai_scope import KNOWN_ENTITY_TYPES, visible_entity_ids_for
from app.services.embedding_store import PostgresArrayEmbeddingStore, ScopeFilter
from app.services.llm_client import EchoLLMClient, LLMClient

_AI_USE = "ai:use"
_AI_ADMIN = "ai:admin"


# ---------------------------------------------------------------- helpers


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _client() -> LLMClient:
    return EchoLLMClient()


def _scope_for(db: Session, user, entity_type: str) -> ScopeFilter | None:
    """Build the retrieval scope as a *query input* (None for admin = all)."""
    if getattr(user, "is_admin", False):
        return None
    return ScopeFilter(entity_type=entity_type, entity_ids=visible_entity_ids_for(entity_type, user, db))


def _event_out(e: OpsEvent) -> dict:
    return {
        "id": e.id,
        "ts": _iso(e.ts),
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "action": e.action,
        "result": e.result,
        "source": e.source,
        "refs": e.refs,
        "trace_id": e.trace_id,
        "created_at": _iso(e.created_at),
    }


def _action_out(a: AiAction) -> dict:
    return {
        "id": a.id,
        "model_name": a.model_name,
        "model_version": a.model_version,
        "input_snapshot": a.input_snapshot,
        "confidence": a.confidence,
        "basis_refs": a.basis_refs,
        "trace_id": a.trace_id,
        "actor": a.actor,
        "decision": a.decision,
        "created_at": _iso(a.created_at),
    }


# ---------------------------------------------------------------- E1 events


def list_events(db: Session, user, filters: dict, page: int, size: int) -> dict:
    require_feature(db, "ai.events")
    user.require_perm(_AI_USE)
    stmt = select(OpsEvent)
    if filters.get("source"):
        stmt = stmt.where(OpsEvent.source == filters["source"])
    if filters.get("entity_type"):
        stmt = stmt.where(OpsEvent.entity_type == filters["entity_type"])
    if filters.get("trace_id"):
        stmt = stmt.where(OpsEvent.trace_id == filters["trace_id"])
    if not getattr(user, "is_admin", False):
        conds = []
        for et in KNOWN_ENTITY_TYPES:
            ids = list(visible_entity_ids_for(et, user, db))
            if ids:
                conds.append(and_(OpsEvent.entity_type == et, OpsEvent.entity_id.in_(ids)))
        if not conds:
            return {"list": [], "total": 0, "page": page, "size": size}
        stmt = stmt.where(or_(*conds))
    rows = list(db.scalars(stmt.order_by(OpsEvent.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {"list": [_event_out(e) for e in rows[start:start + size]], "total": total,
            "page": page, "size": size}


def get_event(db: Session, user, event_id: int) -> dict:
    require_feature(db, "ai.events")
    user.require_perm(_AI_USE)
    e = db.get(OpsEvent, event_id)
    # 404 on missing OR out-of-scope (no existence leak; §27.4 ④ precise 404).
    if e is None:
        raise NotFoundError("event not found")
    if not getattr(user, "is_admin", False):
        ids = visible_entity_ids_for(e.entity_type, user, db)
        if str(e.entity_id) not in ids:
            raise NotFoundError("event not found")
    return _event_out(e)


# ---------------------------------------------------------------- E2 ticket assist


def _get_visible_ticket(db: Session, user, ticket_id: int):
    from app.db.models import Ticket

    t = db.get(Ticket, ticket_id)
    if t is None:
        raise NotFoundError("ticket not found")
    if not getattr(user, "is_admin", False):
        group_ids = list(getattr(user, "visible_group_ids", []) or [])
        allowed = (
            t.requester_id == getattr(user, "id", None)
            or t.assignee_id == getattr(user, "id", None)
            or (t.team_id is not None and t.team_id in group_ids)
        )
        if not allowed:
            raise NotFoundError("ticket not found")
    return t


def ticket_suggest(db: Session, user, ticket_id: int, data) -> dict:
    require_feature(db, "ai.ticket_assist")
    user.require_perm(_AI_USE)
    t = _get_visible_ticket(db, user, ticket_id)
    context = t.title or ""
    if data is not None and getattr(data, "context", None):
        context = f"{context} {data.context}"
    result = _client().complete(
        [{"role": "user", "content": f"工单建议: {context}"}], purpose="ticket_suggest"
    )
    trace_id = f"ticket:{ticket_id}:{int(datetime.now(timezone.utc).timestamp())}"
    db.add(AiAction(
        model_name=result.model_name, model_version=result.model_version,
        input_snapshot={"ticket_id": ticket_id}, confidence=None, basis_refs=[f"ticket:{ticket_id}"],
        trace_id=trace_id, actor=getattr(user, "id", None), decision="auto",
    ))
    db.commit()
    return {"ticket_id": ticket_id, "suggestion": result.text, "model_name": result.model_name,
            "trace_id": trace_id, "authoritative": False}


def ticket_similar(db: Session, user, ticket_id: int, limit: int) -> dict:
    require_feature(db, "ai.ticket_assist")
    user.require_perm(_AI_USE)
    from app.db.models import Ticket

    t = _get_visible_ticket(db, user, ticket_id)
    stmt = select(Ticket).where(Ticket.category == t.category, Ticket.id != t.id)
    rows = list(db.scalars(stmt.order_by(Ticket.id.desc())).all())[:limit]
    return {"ticket_id": ticket_id, "list": [
        {"id": r.id, "ticket_no": r.ticket_no, "title": r.title, "status": r.status} for r in rows
    ], "total": len(rows)}


# ---------------------------------------------------------------- E3 kb RAG


def _fts_hits(db: Session, q: str, scope: ScopeFilter | None, entity_type: str, limit: int) -> list[dict]:
    """Scoped FTS branch (same scope input as the vector branch; ADR#3 C-2)."""
    if entity_type != "kb":
        # No scoped FTS source for other domains => fail-closed.
        return []
    from app.db.models import KbArticle

    stmt = select(KbArticle.id, KbArticle.title).where(KbArticle.title.ilike(f"%{q}%"))
    if scope is not None:
        if not scope.entity_ids:
            return []
        stmt = stmt.where(KbArticle.id.in_([int(i) for i in scope.entity_ids]))
    rows = db.execute(stmt.order_by(KbArticle.id.desc()).limit(limit)).all()
    return [{"doc_ref": str(r[0]), "chunk_ref": f"article:{r[0]}", "title": r[1], "score": 0.0,
             "branch": "fts"} for r in rows]


def kb_semantic_search(db: Session, user, q: str, mode: str, limit: int, entity_type: str | None) -> dict:
    require_feature(db, "ai.kb_assist")
    user.require_perm(_AI_USE)
    et = entity_type or "kb"
    scope = _scope_for(db, user, et)
    if scope is not None and not scope.entity_ids:
        return {"list": [], "total": 0, "mode": mode, "fail_closed": True}
    qvec = _client().embed([q])[0]
    store = PostgresArrayEmbeddingStore(db)
    hits = store.query(qvec, scope=scope, limit=limit)
    out = [{"doc_ref": h.doc_ref, "chunk_ref": h.chunk_ref, "score": round(h.score, 6),
            "branch": "vector"} for h in hits]
    if mode in ("hybrid", "fts"):
        out.extend(_fts_hits(db, q, scope, et, limit))
    dedup: dict[str, dict] = {}
    for item in out:
        dedup.setdefault(item["chunk_ref"], item)
    result = list(dedup.values())[:limit]
    return {"list": result, "total": len(result), "mode": mode}


def kb_answer(db: Session, user, q: str, limit: int, entity_type: str | None) -> dict:
    require_feature(db, "ai.kb_assist")
    user.require_perm(_AI_USE)
    et = entity_type or "kb"
    scope = _scope_for(db, user, et)
    if scope is not None and not scope.entity_ids:
        return {"answer": "", "citations": [], "authoritative": False, "fail_closed": True}
    qvec = _client().embed([q])[0]
    hits = PostgresArrayEmbeddingStore(db).query(qvec, scope=scope, limit=limit)
    citations = [{"doc_ref": h.doc_ref, "chunk_ref": h.chunk_ref, "score": round(h.score, 6)}
                 for h in hits]
    context = "; ".join(c["chunk_ref"] for c in citations)
    result = _client().complete(
        [{"role": "user", "content": f"问题: {q}\n依据: {context}"}], purpose="kb_answer"
    )
    return {"answer": result.text, "citations": citations, "model_name": result.model_name,
            "authoritative": False}


# ---------------------------------------------------------------- E7/E8 governance


def feedback(db: Session, user, data) -> dict:
    require_feature(db, "ai.enabled")
    user.require_perm(_AI_USE)
    decision = getattr(data, "decision", None) or "auto"
    if decision not in AI_ACTION_DECISIONS:
        raise ValidationError(f"decision must be one of {sorted(AI_ACTION_DECISIONS)}")
    row = AiAction(
        model_name=getattr(data, "model_name", None) or "unknown",
        model_version=getattr(data, "model_version", None),
        input_snapshot=getattr(data, "input_snapshot", None),
        confidence=getattr(data, "confidence", None),
        basis_refs=getattr(data, "basis_refs", None),
        trace_id=getattr(data, "trace_id", None),
        actor=getattr(user, "id", None),
        decision=decision,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _action_out(row)


def list_actions(db: Session, user, filters: dict, page: int, size: int) -> dict:
    require_feature(db, "ai.enabled")
    user.require_perm(_AI_ADMIN)
    stmt = select(AiAction)
    if filters.get("decision"):
        stmt = stmt.where(AiAction.decision == filters["decision"])
    if filters.get("trace_id"):
        stmt = stmt.where(AiAction.trace_id == filters["trace_id"])
    rows = list(db.scalars(stmt.order_by(AiAction.id.desc())).all())
    total = len(rows)
    start = (page - 1) * size
    return {"list": [_action_out(a) for a in rows[start:start + size]], "total": total,
            "page": page, "size": size}
