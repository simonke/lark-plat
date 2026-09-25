"""Feature-gate helper for AI capabilities (P4).

Gate order is **feature first** (ticket / workflow / cicd pattern): every public
AI service function calls `require_feature(db, "<flag>")` as its first line, THEN
`user.require_perm("…")` — so with a flag off ANY caller (admin included) gets
400 `feature disabled`. Routes stay registered (openapi keys never shrink).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError
from app.repositories import ConfigRuleRepository

# ai.* flag vocabulary (all default False; `ai.enabled` is the master switch).
AI_FLAGS = ("ai.enabled", "ai.events", "ai.ticket_assist", "ai.kb_assist")


def require_feature(db: Session, flag: str) -> None:
    """Raise 400 `feature disabled` unless `flag` is enabled (default off)."""
    rule = ConfigRuleRepository(db).by_key(flag)
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")
