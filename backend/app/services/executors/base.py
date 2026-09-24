"""Executor abstraction (P2-SS skeleton).

Scope: the executor seam only. Real SSH execution, the Windows ``agent.exe``
build and the ``paramiko`` install are deferred (host environment), so neither
executor here opens a real connection. Approval/sensitivity gates, the
``exec_log`` structure and the WS frames stay owned by the existing agent path
in ``exec_service``; an executor is *selected*, it never dispatches around those
gates.

Frozen contract (seq2191): ``available`` / ``reason`` are attribute-accessible
(plain attribute or ``@property``), ``check(host)`` returns exactly
``{"ok", "latency_ms", "detail"}``.
"""

from __future__ import annotations

from typing import Any, Protocol

CONNECTOR_AGENT = "agent"
CONNECTOR_SSH = "ssh"
CONNECTORS: tuple[str, ...] = (CONNECTOR_AGENT, CONNECTOR_SSH)


class Executor(Protocol):
    """A host execution connector.

    ``check(host)`` probes reachability and returns
    ``{"ok": bool, "latency_ms": int | None, "detail": str}``.
    ``exec(...)`` performs an execution; the skeleton does not execute SSH, and
    the agent path is unchanged (owned by ``exec_service``).
    """

    name: str
    available: bool
    reason: str | None

    def check(self, host: Any) -> dict[str, Any]: ...

    def exec(self, *args: Any, **kwargs: Any) -> Any: ...
