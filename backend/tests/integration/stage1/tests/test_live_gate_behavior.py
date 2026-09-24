"""Offline behavior tests for the stage1 live gate (backend, arch seq2349 / req seq2354-2).

Proves — with no network, no live server and no DB contact — that the harness
distinguishes a **reachable server error (5xx → fail)** from a **transport error /
disabled live mode (NOT RUN → skip)**. This is the regression that keeps the live
gate from silently turning green (backend seq2344).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

_CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
_spec = importlib.util.spec_from_file_location("stage1_conftest", _CONFTEST)
assert _spec and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def test_client_error_does_not_fail():
    # 4xx is a legitimate application response, not a server fault.
    gate._fail_on_server_error(httpx.Response(403, text="forbidden"), "GET /x")


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_error_fails(status):
    with pytest.raises(pytest.fail.Exception) as excinfo:
        gate._fail_on_server_error(
            httpx.Response(status, text='{"code":500}'), "POST /auth/login"
        )
    assert f"HTTP {status}" in str(excinfo.value)
    assert "server error" in str(excinfo.value)


def test_skip_live_when_disabled_is_not_run(monkeypatch):
    monkeypatch.setattr(gate, "LIVE_ENABLED", False)
    with pytest.raises(pytest.skip.Exception) as excinfo:
        gate._skip_live()
    assert "NOT RUN" in str(excinfo.value)


def test_skip_live_when_unreachable_is_not_run(monkeypatch):
    monkeypatch.setattr(gate, "LIVE_ENABLED", True)
    monkeypatch.setattr(gate, "API_BASE", "http://127.0.0.1:9/api/v1")
    with pytest.raises(pytest.skip.Exception) as excinfo:
        gate._skip_live()
    assert "NOT RUN" in str(excinfo.value)
