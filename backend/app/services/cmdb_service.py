"""CMDB service (P3-3): `entity_relation` CRUD + topology / impact analysis.

Behaviour is gated by the ``feature.cmdb_topology`` flag (default False -> 400,
mirrors ``ticket_service._require_feature``) and every read/write is scoped by
the US-03 data permission seam (``HostRepository.visible_entity_ids``). A
non-admin caller must see BOTH endpoints of a relation to write (add/delete) it,
else **403**; topology/impact results are clipped to visible entities.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.db.models import AssetGroup, Host
from app.db.models.cmdb import ENTITY_TYPES, REL_TYPES, EntityRelation
from app.repositories import ConfigRuleRepository, HostRepository
from app.schemas import asset as sch

_DEPTH_DEFAULT = 2
_DEPTH_MAX = 3
_DIRECTIONS = ("up", "down", "both")

# (visible host-id str set | None=unrestricted, visible group-id set | None)
_Scope = tuple["set[str] | None", "set[int] | None"]


# ---------------------------------------------------------------- helpers


def _require_feature(db: Session) -> None:
    """feature.cmdb_topology gates behaviour (not routes); default False => 400."""
    rule = ConfigRuleRepository(db).by_key("feature.cmdb_topology")
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")


def _visible_scope(db: Session, user) -> _Scope:
    """US-03 seam: (host entity-id set, group-id set); None element = unrestricted."""
    if getattr(user, "is_admin", False):
        return None, None
    groups = list(getattr(user, "visible_group_ids", None) or [])
    return set(HostRepository(db).visible_entity_ids(groups)), set(groups)


def _entity_visible(scope: _Scope, etype: str, eid: int) -> bool:
    hosts, groups = scope
    if etype == "host":
        return hosts is None or str(eid) in hosts
    if etype == "host_group":
        return groups is None or eid in groups
    return hosts is None and groups is None


def _clamp_depth(depth: int | None) -> int:
    if depth is None:
        return _DEPTH_DEFAULT
    if depth < 0 or depth > _DEPTH_MAX:
        raise ValidationError(f"depth must be 0..{_DEPTH_MAX}")
    return depth


def _check_direction(direction: str | None) -> str:
    d = direction or "both"
    if d not in _DIRECTIONS:
        raise ValidationError(f"direction must be one of {sorted(_DIRECTIONS)}")
    return d


def _validate_create(data: sch.RelationCreate) -> None:
    if data.src_type not in ENTITY_TYPES or data.dst_type not in ENTITY_TYPES:
        raise ValidationError(f"entity_type must be one of {sorted(ENTITY_TYPES)}")
    if data.rel_type not in REL_TYPES:
        raise ValidationError(f"rel_type must be one of {sorted(REL_TYPES)}")
    if data.src_type == data.dst_type and data.src_id == data.dst_id:
        raise ValidationError("self relation is not allowed")


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _relation_out(r: EntityRelation) -> dict:
    return {
        "id": r.id,
        "src_type": r.src_type,
        "src_id": r.src_id,
        "dst_type": r.dst_type,
        "dst_id": r.dst_id,
        "rel_type": r.rel_type,
        "properties": r.properties,
        "remark": r.remark,
        "created_by": r.created_by,
        "created_at": _iso(r.created_at),
        "updated_at": _iso(r.updated_at),
    }


def _labels(db: Session, keys: set[tuple[str, int]]) -> dict[tuple[str, int], str]:
    host_ids = [i for t, i in keys if t == "host"]
    group_ids = [i for t, i in keys if t == "host_group"]
    out: dict[tuple[str, int], str] = {}
    if host_ids:
        for h in db.scalars(select(Host).where(Host.id.in_(host_ids))).all():
            out[("host", h.id)] = h.hostname or h.ip
    if group_ids:
        for g in db.scalars(select(AssetGroup).where(AssetGroup.id.in_(group_ids))).all():
            out[("host_group", g.id)] = g.name
    return out


def _edges_for(
    db: Session, node: tuple[str, int], direction: str, rel_types: list[str] | None
) -> list[EntityRelation]:
    etype, eid = node
    stmt = select(EntityRelation)
    if rel_types:
        stmt = stmt.where(EntityRelation.rel_type.in_(rel_types))
    if direction == "down":
        stmt = stmt.where(EntityRelation.src_type == etype, EntityRelation.src_id == eid)
    elif direction == "up":
        stmt = stmt.where(EntityRelation.dst_type == etype, EntityRelation.dst_id == eid)
    else:  # both
        stmt = stmt.where(
            or_(
                and_(EntityRelation.src_type == etype, EntityRelation.src_id == eid),
                and_(EntityRelation.dst_type == etype, EntityRelation.dst_id == eid),
            )
        )
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------- relations


def list_relations(
    db: Session,
    user,
    filters: dict[str, Any],
    page: int,
    size: int,
) -> dict:
    _require_feature(db)
    stmt = select(EntityRelation)
    for field in ("src_type", "src_id", "dst_type", "dst_id", "rel_type"):
        value = filters.get(field)
        if value is not None:
            stmt = stmt.where(getattr(EntityRelation, field) == value)
    rows = list(db.scalars(stmt.order_by(EntityRelation.id.desc())).all())

    scope = _visible_scope(db, user)
    rows = [
        r for r in rows
        if _entity_visible(scope, r.src_type, r.src_id)
        and _entity_visible(scope, r.dst_type, r.dst_id)
    ]
    total = len(rows)
    start = (page - 1) * size
    page_rows = rows[start:start + size]
    return {
        "list": [_relation_out(r) for r in page_rows],
        "total": total,
        "page": page,
        "size": size,
    }


def create_relation(db: Session, user, data: sch.RelationCreate) -> dict:
    _require_feature(db)
    _validate_create(data)
    scope = _visible_scope(db, user)
    # US-03 write path: caller must see BOTH src AND dst, else 403.
    if not (
        _entity_visible(scope, data.src_type, data.src_id)
        and _entity_visible(scope, data.dst_type, data.dst_id)
    ):
        raise ForbiddenError("relation endpoints not visible to caller")

    existing = db.scalar(
        select(EntityRelation).where(
            EntityRelation.src_type == data.src_type,
            EntityRelation.src_id == data.src_id,
            EntityRelation.dst_type == data.dst_type,
            EntityRelation.dst_id == data.dst_id,
            EntityRelation.rel_type == data.rel_type,
        )
    )
    if existing is not None:
        return _relation_out(existing)  # idempotent: repeat -> existing row (200)

    row = EntityRelation(
        src_type=data.src_type,
        src_id=data.src_id,
        dst_type=data.dst_type,
        dst_id=data.dst_id,
        rel_type=data.rel_type,
        properties=data.properties,
        remark=data.remark,
        created_by=getattr(user, "id", None),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _relation_out(row)


def delete_relation(db: Session, user, relation_id: int) -> None:
    _require_feature(db)
    row = db.get(EntityRelation, relation_id)
    if row is None:
        raise NotFoundError("relation not found")
    scope = _visible_scope(db, user)
    if not (
        _entity_visible(scope, row.src_type, row.src_id)
        and _entity_visible(scope, row.dst_type, row.dst_id)
    ):
        raise ForbiddenError("relation endpoints not visible to caller")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------- topology / impact


def topology(
    db: Session,
    user,
    entity_type: str,
    entity_id: int,
    direction: str | None,
    depth: int | None,
    rel_types: list[str] | None,
) -> dict:
    _require_feature(db)
    direction = _check_direction(direction)
    depth = _clamp_depth(depth)
    scope = _visible_scope(db, user)
    root = (entity_type, entity_id)

    node_role: dict[tuple[str, int], str] = {root: "root"}
    edge_map: dict[tuple, dict] = {}
    order: list[tuple[str, int]] = [root]
    frontier = [root]
    truncated = False
    for level in range(depth):
        nxt: list[tuple[str, int]] = []
        for node in frontier:
            for r in _edges_for(db, node, direction, rel_types):
                skey = (r.src_type, r.src_id)
                dkey = (r.dst_type, r.dst_id)
                ekey = (r.src_type, r.src_id, r.dst_type, r.dst_id, r.rel_type)
                if ekey not in edge_map:
                    edge_map[ekey] = {
                        "src": {"type": r.src_type, "id": r.src_id},
                        "dst": {"type": r.dst_type, "id": r.dst_id},
                        "rel_type": r.rel_type,
                    }
                other = dkey if skey == node else skey
                if other not in node_role:
                    node_role[other] = "down" if skey == node else "up"
                    order.append(other)
                    nxt.append(other)
        if level == depth - 1 and nxt:
            truncated = True
        frontier = nxt
        if not frontier:
            break

    keep = {k for k in order if _entity_visible(scope, k[0], k[1])}
    labels = _labels(db, keep)
    nodes = [
        {"type": k[0], "id": k[1], "label": labels.get(k, ""), "role": node_role[k]}
        for k in order
        if k in keep
    ]
    edges = [
        e for e in edge_map.values()
        if _entity_visible(scope, e["src"]["type"], e["src"]["id"])
        and _entity_visible(scope, e["dst"]["type"], e["dst"]["id"])
    ]
    return {"nodes": nodes, "edges": edges, "truncated": truncated}


def impact(
    db: Session,
    user,
    entity_type: str,
    entity_id: int,
    direction: str | None,
    depth: int | None,
    rel_types: list[str] | None,
) -> dict:
    _require_feature(db)
    direction = _check_direction(direction if direction is not None else "down")
    depth = _clamp_depth(depth)
    scope = _visible_scope(db, user)
    root = (entity_type, entity_id)

    visited = {root}
    order: list[tuple[str, int]] = []
    frontier = [root]
    truncated = False
    for level in range(depth):
        nxt: list[tuple[str, int]] = []
        for node in frontier:
            for r in _edges_for(db, node, direction, rel_types):
                skey = (r.src_type, r.src_id)
                dkey = (r.dst_type, r.dst_id)
                other = dkey if skey == node else skey
                if other not in visited:
                    visited.add(other)
                    order.append(other)
                    nxt.append(other)
        if level == depth - 1 and nxt:
            truncated = True
        frontier = nxt
        if not frontier:
            break

    affected = [k for k in order if _entity_visible(scope, k[0], k[1])]
    labels = _labels(db, set(affected) | {root})
    return {
        "root": {
            "type": root[0], "id": root[1], "label": labels.get(root, ""),
        },
        "affected": [
            {"type": k[0], "id": k[1], "label": labels.get(k, "")} for k in affected
        ],
        "count": len(affected),
        "truncated": truncated,
    }
