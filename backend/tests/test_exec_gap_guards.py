"""Negative guards for the chain-③ exec G-gaps (G1/G2/G4/G5/G8).

Architect-confirmed landing scope (see exec gap self-check): these guards pin the
fixed behaviour so the fixes cannot silently regress. Source-shape guards are used
where a fix is structural (matching the repo-wide D3-*/D11-* guard convention); a
few behavioural guards exercise the pure helpers directly.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_BACKEND = Path(__file__).resolve().parents[1]
TASKS_SRC = (REPO_BACKEND / "app" / "tasks" / "exec_tasks.py").read_text(encoding="utf-8")
EXEC_SRC = (REPO_BACKEND / "app" / "services" / "exec_service.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- G1


def test_resolve_content_uses_script_version_real_content():
    """G1: kind=script must resolve ScriptVersion.content, not a hardcoded placeholder."""
    assert "script placeholder" not in TASKS_SRC, (
        "G1: hardcoded script placeholder must be gone from exec_tasks.py"
    )
    assert "ScriptVersionRepository" in TASKS_SRC, (
        "G1: ScriptVersionRepository must be used to resolve script content"
    )
    assert "by_script_version" in TASKS_SRC, (
        "G1: content must come from the pinned script_version (fallback current_version)"
    )


def test_render_params_replaces_placeholders():
    """G1: {{key}} params are rendered into the resolved content."""
    from app.tasks.exec_tasks import _render_params

    assert _render_params("echo {{host}}", {"host": "web-1"}) == "echo web-1"
    assert _render_params("no placeholders", {"host": "web-1"}) == "no placeholders"
    assert _render_params("{{missing}}", {"other": "x"}) == "{{missing}}"


# ---------------------------------------------------------------- G2


def test_persist_logs_broadcasts_realtime_frame():
    """G2: exec_log ingestion must push a /ws/exec realtime log frame to the UI."""
    agent_ws_src = (REPO_BACKEND / "app" / "ws" / "agent_ws.py").read_text(encoding="utf-8")
    body = agent_ws_src[agent_ws_src.index("async def _persist_logs"):agent_ws_src.index("async def _persist_result")]
    assert '"type": "log"' in body, (
        "G2: _persist_logs must broadcast a {'type':'log',...} frame over /ws/exec"
    )
    assert "await broadcast(" in body, (
        "G2: _persist_logs must call the exec broadcast"
    )
    assert "repo.append(" in body, "G2: exec_log must still be persisted (not only broadcast)"


def test_persist_result_finalizes_and_broadcasts_status():
    """G2: exec_result must broadcast a status/result frame, not just persist."""
    agent_ws_src = (REPO_BACKEND / "app" / "ws" / "agent_ws.py").read_text(encoding="utf-8")
    body = agent_ws_src[agent_ws_src.index("async def _persist_result"):agent_ws_src.index("def _maybe_finalize_task")]
    assert '"type": "result"' in body, (
        "G2: _persist_result must broadcast a result frame"
    )
    assert '"type": "status"' in body, (
        "G2: _persist_result must broadcast a status frame"
    )
    assert "update_status(" in body, "G2: _persist_result must still finalize DB state"


# ---------------------------------------------------------------- G4


def test_stop_task_dispatches_agent_stop_frame():
    """G4: stop must not only flip DB state - it must tell a running agent to stop."""
    assert "_send_agent_stop" in EXEC_SRC, (
        "G4: stop must route an S->C stop frame to the running agent"
    )
    assert '"type": "stop"' in TASKS_SRC or '"type": "stop"' in EXEC_SRC, (
        "G4: an agent stop frame must be constructed"
    )


def test_dispatch_sends_exec_frame_to_live_agent():
    """G4: a dispatch path must exist that hands the exec frame to a live agent."""
    assert "_dispatch_exec_frame" in TASKS_SRC, (
        "G4: exec must be dispatched to a connected agent, not only mocked"
    )
    assert "dispatch_to_agent_sync" in TASKS_SRC, (
        "G4: exec frames must reach the agent gateway"
    )


# ---------------------------------------------------------------- G5


def test_exec_dispatch_releases_semaphores_in_finally():
    """G5: acquired global/host semaphores must be released via finally so no leak."""
    # finally block must release both semaphores after starting a host
    assert "finally:" in TASKS_SRC
    assert TASKS_SRC.count("release_semaphore") >= TASKS_SRC.count("acquire_semaphore"), (
        "G5: every acquire must have a matching release (no signal leak)"
    )


def test_scan_timeouts_only_matches_running_state():
    """G5/G8: timeout sweep must only act on 'running' tasks (not awaiting_approval)."""
    assert 'status == "running"' in TASKS_SRC, (
        "G5: timeout scan must only consider running tasks"
    )


# ---------------------------------------------------------------- G8


def test_retry_revalidates_sensitivity():
    """G8: retry must re-check sensitivity (config may have changed since run)."""
    assert "detect_sensitive" in EXEC_SRC, (
        "G8: retry must re-run sensitive detection before re-dispatching"
    )
    # retry must route a sensitive task back to awaiting_approval + create an approval
    assert "awaiting_approval" in EXEC_SRC
    assert "ApprovalRequest(" in EXEC_SRC


def test_retry_closes_orphan_approval():
    """G8: retry must close any orphaned pending approval instead of leaving it open."""
    assert "_close_orphan_approval" in EXEC_SRC, (
        "G8: retry must close orphan approvals"
    )
