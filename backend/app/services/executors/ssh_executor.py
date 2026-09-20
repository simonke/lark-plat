"""SSH executor skeleton.

``paramiko`` is a soft dependency imported lazily: when it is absent the
executor reports ``available is False`` / ``reason == "paramiko not installed"``
without importing anything at module load, so the module stays offline
deterministic and has no hard dependency. Real SSH sessions are deferred to the
release phase (``paramiko`` install on the D: drive).
"""

from __future__ import annotations

from typing import Any

PARAMIKO_MISSING_REASON = "paramiko not installed"


def _load_paramiko() -> Any | None:
    """Import paramiko lazily; return ``None`` when the optional dep is absent."""
    try:
        import paramiko
    except ImportError:
        return None
    return paramiko


class SSHExecutor:
    """SSH connector. Skeleton: availability probe only, no live session."""

    name = "ssh"

    @property
    def available(self) -> bool:
        # property (attribute-accessible, lazily evaluated): seq2191 allows
        # either a plain attribute or @property, as long as no () is required.
        return _load_paramiko() is not None

    @property
    def reason(self) -> str | None:
        return None if self.available else PARAMIKO_MISSING_REASON

    def check(self, host: Any) -> dict[str, Any]:
        if not self.available:
            return {"ok": False, "latency_ms": None,
                    "detail": f"ssh connector unavailable: {PARAMIKO_MISSING_REASON}"}
        raise NotImplementedError("ssh connectivity check not implemented in skeleton")

    def exec(self, *args: Any, **kwargs: Any) -> Any:
        if not self.available:
            raise NotImplementedError(
                f"ssh executor unavailable: {PARAMIKO_MISSING_REASON}"
            )
        raise NotImplementedError("ssh execution not implemented in skeleton")


ssh_executor = SSHExecutor()
