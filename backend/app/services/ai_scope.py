"""US-03 entity-visibility dispatcher (P4 ADR#3).

`visible_entity_ids_for(entity_type, actor, db)` maps an actor to the set of
entity identifiers they are allowed to retrieve for a given entity type. The
result feeds `ScopeFilter.entity_ids` and is pushed into the retrieval layer as a
*query input* — never applied as a post-filter.

Host reuse: `HostRepository.visible_entity_ids` (the existing US-03 seam) returns
the ip ∪ hostname ∪ str(id) identifiers for the actor's visible groups.
**Unknown / undefined entity types are fail-closed (empty set).**
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.repositories import HostRepository

# The dispatcher handles these entity types; anything else is fail-closed.
KNOWN_ENTITY_TYPES = ("host", "ticket", "kb", "audit")

# P5 US-03: explicit public/wildcard scope token. KB scope ALWAYS includes it so
# `visibility=public` articles are retrievable by every actor (NOT NULL literal;
# never a post-filter — it is part of the scope pushed into the retrieval layer).
GLOBAL_SCOPE_TOKEN = "__public__"


def _visible_hosts(db: Session, actor) -> frozenset[str]:
    if getattr(actor, "is_admin", False):
        from app.db.models import Host

        rows = db.execute(select(Host.id, Host.hostname, Host.ip)).all()
    else:
        group_ids = list(getattr(actor, "visible_group_ids", []) or [])
        return _stringify(HostRepository(db).visible_entity_ids(group_ids))
    out: set[str] = set()
    for host_id, hostname, ip in rows:
        if ip:
            out.add(str(ip))
        if hostname:
            out.add(str(hostname))
        out.add(str(host_id))
    return frozenset(out)


def _visible_tickets(db: Session, actor) -> frozenset[str]:
    from app.db.models import Ticket

    user_id = getattr(actor, "id", None)
    group_ids = list(getattr(actor, "visible_group_ids", []) or [])
    stmt = select(Ticket.id)
    if not getattr(actor, "is_admin", False):
        conds = [Ticket.requester_id == user_id, Ticket.assignee_id == user_id]
        if group_ids:
            conds.append(Ticket.team_id.in_(group_ids))
        from sqlalchemy import or_

        stmt = stmt.where(or_(*conds))
    return frozenset(str(r[0]) for r in db.execute(stmt).all())


def _visible_kb(db: Session, actor) -> frozenset[str]:
    from app.db.models import KbArticle

    stmt = select(KbArticle.id)
    if not getattr(actor, "is_admin", False):
        from sqlalchemy import or_

        stmt = stmt.where(
            or_(
                KbArticle.visibility.in_(("public", "internal")),
                KbArticle.author_id == getattr(actor, "id", None),
            )
        )
    ids = {str(r[0]) for r in db.execute(stmt).all()}
    # P5 US-03 double proof: the explicit public wildcard is ALWAYS in kb scope.
    ids.add(GLOBAL_SCOPE_TOKEN)
    return frozenset(ids)


def _stringify(values) -> frozenset[str]:
    return frozenset(str(v) for v in (values or []))


def visible_entity_ids_for(entity_type: str, actor, db: Session | None = None) -> frozenset[str]:
    """Return the actor's visible entity ids for ``entity_type`` (fail-closed)."""
    if db is None or actor is None:
        return frozenset()
    if entity_type == "host":
        return _visible_hosts(db, actor)
    if entity_type == "ticket":
        return _visible_tickets(db, actor)
    if entity_type == "kb":
        return _visible_kb(db, actor)
    if entity_type == "audit":
        # Audit visibility is admin-gated; non-admins see nothing here.
        return frozenset() if not getattr(actor, "is_admin", False) else frozenset({"*"})
    # Undefined entity type => fail-closed (reject all).
    return frozenset()
