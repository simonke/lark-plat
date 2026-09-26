"""E4 AIOps RCA service (P5): read-time alert correlation + root-cause candidates.

**NO new table** (tuple v1->r2 seq3332): `aggregate` correlates existing
`mon_alert` rows at read time; `run` walks the CMDB topology through the P3-3
`cmdb_service` seam (`_clamp_depth` + layered traversal via `impact`) — this is
NOT a second BFS. Results are non-authoritative advisory candidates; the AI never
executes or bypasses approval.

Depth domain mirrors `cmdb_service`: `0..3`, default 2, `0` legal, `<0`/`>3` raise
422. Association traversal is cycle-safe (cmdb_service tracks visited nodes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import MON_LEVELS, MonAlert
from app.services import cmdb_service
from app.services.ai_gate import require_feature

_AI_USE = "ai:use"
# E4 severity rank — single source of truth (`app/db/models/monitor.py`, imported,
# never re-declared). Index order defines "max" (higher == more severe).
_SEVERITY_RANK = {lvl: i for i, lvl in enumerate(MON_LEVELS)}


@dataclass
class RcaCandidate:
    """One advisory root-cause candidate (never authoritative)."""

    entity_type: str
    entity_id: str
    score: float
    reason: str
    evidence: list = field(default_factory=list)


@dataclass
class RcaReport:
    """E4 report envelope (plain-dict convertible; stored nowhere — read-time)."""

    alert_id: int | None
    root_entity: dict
    depth: int
    candidates: list = field(default_factory=list)
    generated_at: str = ""
    authoritative: bool = False

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "root_entity": self.root_entity,
            "depth": self.depth,
            "candidates": [
                {
                    "entity_type": c.entity_type,
                    "entity_id": c.entity_id,
                    "score": c.score,
                    "reason": c.reason,
                    "evidence": c.evidence,
                }
                for c in self.candidates
            ],
            "generated_at": self.generated_at,
            "authoritative": False,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_id(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _window_rule(a) -> str:
    """Aggregate window `rule` value: `rule_id` -> `rule_name` -> ``""``."""
    if a.rule_id is not None:
        return str(a.rule_id)
    return getattr(a, "rule_name", "") or ""


def aggregate(db: Session, user, filters: dict | None = None, page: int = 1, size: int = 20) -> dict:
    """Read-time alert aggregation (NO new table). Scoped via the monitor seam.

    Window = `(entity_type, entity_id, rule)` (tuple §五.1 / §29.8); `rule` falls
    back `rule_id` -> `rule_name` -> `""`. `max_severity` = TRUE max over the
    `MON_LEVELS` single source (None/unknown == lowest; all-None => None).
    """
    require_feature(db, "ai.rca")
    user.require_perm(_AI_USE)
    filters = dict(filters or {})

    rows = list(db.scalars(select(MonAlert).order_by(MonAlert.id.desc())).all())
    # US-03: reuse the monitor entity-scope seam (None => unrestricted/admin).
    from app.services import monitor_service

    visible = monitor_service._visible_entity_ids(db, user)
    if visible is not None:
        vis = set(visible)
        rows = [a for a in rows if str((a.entity or {}).get("entity_id")) in vis]
    if filters.get("status"):
        rows = [a for a in rows if a.status == filters["status"]]
    if filters.get("severity"):
        rows = [a for a in rows if a.severity == filters["severity"]]

    by_window: dict[tuple, dict] = {}
    for a in rows:
        entity = a.entity or {}
        rule = _window_rule(a)
        key = (entity.get("entity_type"), str(entity.get("entity_id")), rule)
        bucket = by_window.get(key)
        if bucket is None:
            bucket = {
                "entity_type": entity.get("entity_type"),
                "entity_id": str(entity.get("entity_id")),
                "rule": rule,
                "count": 0,
                "max_severity": None,
                "alert_ids": [],
            }
            by_window[key] = bucket
        bucket["count"] += 1
        bucket["alert_ids"].append(a.id)
        rank = _SEVERITY_RANK.get(a.severity, -1)
        if rank > _SEVERITY_RANK.get(bucket["max_severity"], -1):
            bucket["max_severity"] = a.severity if rank >= 0 else None

    grouped = sorted(
        by_window.values(),
        key=lambda b: (-b["count"], str(b["entity_type"]), b["entity_id"], b["rule"]),
    )
    total = len(grouped)
    start = (page - 1) * size
    return {
        "list": grouped[start:start + size],
        "total": total,
        "page": page,
        "size": size,
        "generated_at": _now_iso(),
        "authoritative": False,
    }


def run(db: Session, user, alert_id: int, depth: int | None = None) -> dict:
    """Correlate one alert against CMDB topology (reuses `cmdb_service`)."""
    require_feature(db, "ai.rca")
    user.require_perm(_AI_USE)
    alert = db.get(MonAlert, alert_id)
    if alert is None:
        raise NotFoundError("alert not found")

    entity = alert.entity or {}
    etype = entity.get("entity_type") or "host"
    eid = _coerce_id(entity.get("entity_id"))
    depth_n = cmdb_service._clamp_depth(depth)

    candidates: list[RcaCandidate] = []
    if eid is not None:
        impact = cmdb_service.impact(db, user, etype, eid, "down", depth_n, None)
        for item in impact.get("affected", []):
            candidates.append(
                RcaCandidate(
                    entity_type=item.get("type", ""),
                    entity_id=str(item.get("id", "")),
                    score=1.0,
                    reason="downstream-of-alert-entity",
                    evidence=[{"rule_id": alert.rule_id, "severity": alert.severity}],
                )
            )

    report = RcaReport(
        alert_id=alert_id,
        root_entity={"type": etype, "id": entity.get("entity_id"),
                     "name": entity.get("entity_name")},
        depth=depth_n,
        candidates=candidates,
        generated_at=_now_iso(),
    )
    return report.to_dict()
