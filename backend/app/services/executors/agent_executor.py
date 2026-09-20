"""Agent executor: wraps the existing heartbeat-based connectivity semantics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

HEARTBEAT_FRESH_SECONDS = 90


class AgentExecutor:
    """Agent connector. ``check`` reproduces the pre-P2-SS agent branch verbatim."""

    name = "agent"

    def available(self) -> bool:
        return True

    def reason(self) -> str | None:
        return None

    def check(self, host: Any) -> dict[str, Any]:
        last = getattr(host, "last_heartbeat_at", None)
        if not last:
            return {"ok": False, "latency_ms": 0, "detail": "no agent"}
        age = (datetime.now(timezone.utc) - last).total_seconds()
        if age <= HEARTBEAT_FRESH_SECONDS:
            return {"ok": True, "latency_ms": 0,
                    "detail": f"agent online, heartbeat {int(age)}s ago"}
        return {"ok": False, "latency_ms": 0,
                "detail": f"agent stale, last heartbeat {int(age)}s ago"}

    def exec(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "agent execution is dispatched by exec_service (unchanged by P2-SS)"
        )
