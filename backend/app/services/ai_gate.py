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
AI_FLAGS = (
    "ai.enabled", "ai.events", "ai.ticket_assist", "ai.kb_assist",
    "ai.rca", "ai.playbook", "ai.auto_remediate",
)


def is_feature_enabled(db: Session, flag: str) -> bool:
    """Silent probe (never raises). For SHARED P5 paths where a flag-off must stay
    byte-identical — e.g. the E6 auto-policy seam inside `create_exec_task_record`,
    which must NOT emit a 400/403 for ordinary exec creation (P6 r1 constraint ①)."""
    rule = ConfigRuleRepository(db).by_key(flag)
    return bool((rule.rule_value or {}).get("value", False)) if rule else False


def require_feature(db: Session, flag: str) -> None:
    """Raise 400 `feature disabled` unless `flag` is enabled (default off)."""
    if not is_feature_enabled(db, flag):
        raise BadRequestError("feature disabled")
