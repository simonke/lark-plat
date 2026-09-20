"""Executor registry + degraded routing decision (P2-SS skeleton)."""

from __future__ import annotations

from typing import Any

from app.services.executors.agent_executor import AgentExecutor, agent_executor
from app.services.executors.base import (
    CONNECTORS,
    CONNECTOR_AGENT,
    CONNECTOR_SSH,
    Executor,
)
from app.services.executors.ssh_executor import SSHExecutor, ssh_executor

_EXECUTORS: dict[str, Executor] = {
    CONNECTOR_AGENT: agent_executor,
    CONNECTOR_SSH: ssh_executor,
}


def build_executor(name: str) -> Executor:
    return _EXECUTORS[name]


def all_executors() -> list[Executor]:
    # Resolve via build_executor every call so monkeypatching the frozen
    # injection seam (build_executor) also drives infos/availability.
    return [build_executor(name) for name in CONNECTORS]


def executor_infos() -> list[dict[str, Any]]:
    return [
        {"name": ex.name, "available": ex.available, "reason": ex.reason}
        for ex in all_executors()
    ]


def available_executors() -> list[str]:
    return [ex.name for ex in all_executors() if ex.available]


def resolve_executor(connector: str, *, ssh_fallback: bool = False) -> str:
    """Degraded routing decision for a host's connector.

    A host pinned to ssh stays ssh; an unknown connector passes through
    unchanged (so the default path keeps ``ExecTaskHost.executor == host.connector``
    byte-for-byte). An agent host only routes to ssh when the
    ``executor.ssh_fallback`` config_rule is on AND ssh is actually usable
    (``paramiko`` present); otherwise it stays on the agent path.
    """
    if connector == CONNECTOR_AGENT and ssh_fallback and build_executor(CONNECTOR_SSH).available:
        return CONNECTOR_SSH
    return connector


__all__ = [
    "CONNECTOR_AGENT",
    "CONNECTOR_SSH",
    "CONNECTORS",
    "AgentExecutor",
    "Executor",
    "SSHExecutor",
    "agent_executor",
    "all_executors",
    "available_executors",
    "build_executor",
    "executor_infos",
    "resolve_executor",
    "ssh_executor",
]
