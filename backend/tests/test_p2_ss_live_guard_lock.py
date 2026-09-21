"""P2-SS live-guard lock (unit lane, off `6d0e2db`, add-only, new SHA).

WHY (backend seq2261 / architect seq2263, adopt option (b)):
  Installing `paramiko` makes `SSHExecutor.available` True, but the skeleton
  `check()` then `raise NotImplementedError`, and `asset_service.connectivity_check`
  (ssh branch, `asset_service.py:278-279`) has no try/except -> live ssh
  connectivity probe returns HTTP 500.

  This is NOT merely "unimplemented": the frozen contract (seq2191) says
  `check(host)` returns exactly `{ok, latency_ms, detail}`. Raising in the
  available state VIOLATES that frozen contract. The offline unit gate missed it
  because the existing lock only asserts the keyset in the `available=False`
  branch.

GUARD CONTRACT (frozen by architect seq2263):
  - `SSHExecutor.check(host)` must NEVER raise and must ALWAYS return exactly
    `{ok, latency_ms, detail}` in BOTH available states. When available but not
    implemented -> degraded `{ok: False, latency_ms: None, detail: <non-empty str>}`.
  - `asset_service.connectivity_check` must never let an executor exception
    escape (never 500); any executor error -> degraded `ok=False`.
  - `executor.ssh_fallback` default stays False; `check` subkey set unchanged
    (NOT a contract change).

DELIBERATE NON-PINS (avoid the head-pin style maintenance hazard):
  - The exact `detail` string is NOT asserted (only non-empty str) so wording
    may evolve without red-ing this lock.
  - `exec()` is NOT asserted here: it stays `NotImplementedError` for the guard
    batch but WILL be implemented in the true-machine batch; pinning it would
    create a false red later.

Evidence boundary (hard): offline pure fake, NO real SSH. Real SSH / `agent.exe`
/ `paramiko` on D: are deferred (list C) and must not be claimed here.

Run from the backend checkout:
    python -m pytest tests/test_p2_ss_live_guard_lock.py -p no:cacheprovider -q
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

_CHECK_KEYS = {"ok", "latency_ms", "detail"}


def _module(name: str):
    try:
        return importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"P2-SS live-guard lock: {name} unavailable: {exc}")


def _ssh_module():
    return _module("app.services.executors.ssh_executor")


def _executor_instance(mod):
    for name in ("SSHExecutor", "SshExecutor"):
        cls = getattr(mod, name, None)
        if isinstance(cls, type):
            try:
                return cls()
            except Exception:  # noqa: BLE001
                pass
    for name in ("ssh_executor", "SSH_EXECUTOR", "executor"):
        obj = getattr(mod, name, None)
        if obj is not None and not isinstance(obj, type):
            return obj
    pytest.fail("P2-SS live-guard lock: SSH executor object not found")


def _force_available(mod, monkeypatch, present: bool):
    """Drive `available` deterministically by stubbing the lazy loader."""
    monkeypatch.setattr(mod, "_load_paramiko", (lambda: object()) if present else (lambda: None))


def _mount_fake_host(asset, monkeypatch, connector: str):
    """Fake HostRepository(db) -> repo with .get() returning a visible host row."""
    host = SimpleNamespace(connector=connector, id=1, status=None)
    monkeypatch.setattr(
        asset, "HostRepository",
        lambda db: SimpleNamespace(get=lambda host_id: host),
    )
    monkeypatch.setattr(asset, "_host_visible", lambda user, row: True)
    return host


# ── G1: available=False branch stays contract-compliant (regression guard) ────

def test_g1_check_returns_keyset_when_absent(monkeypatch):
    mod = _ssh_module()
    obj = _executor_instance(mod)
    _force_available(mod, monkeypatch, present=False)
    assert obj.available is False
    # absent-state reason literal is the seq2191 canonical freeze (pinned, not soft)
    assert obj.reason == "paramiko not installed", repr(obj.reason)
    res = obj.check(SimpleNamespace(connector="ssh", id=1))
    assert isinstance(res, dict)
    assert set(res) == _CHECK_KEYS, set(res)
    assert res["ok"] is False


# ── G2: available=True must NOT raise; must return the frozen keyset (RED pre-guard)

def test_g2_check_never_raises_and_returns_keyset_when_available(monkeypatch):
    mod = _ssh_module()
    obj = _executor_instance(mod)
    _force_available(mod, monkeypatch, present=True)
    assert obj.available is True, "stub failed to drive available=True"

    try:
        res = obj.check(SimpleNamespace(connector="ssh", id=1))
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "SSHExecutor.check(host) must never raise (frozen contract returns "
            f"exactly {sorted(_CHECK_KEYS)}); got {type(exc).__name__}: {exc}"
        )

    assert isinstance(res, dict)
    assert set(res) == _CHECK_KEYS, set(res)
    # degraded-but-not-implemented: ok False, latency None, non-empty detail
    # (exact detail wording intentionally NOT pinned)
    assert res["ok"] is False, res
    assert res["latency_ms"] is None, res
    assert isinstance(res["detail"], str) and res["detail"], res


def test_g2b_available_and_reason_contract_when_present(monkeypatch):
    mod = _ssh_module()
    obj = _executor_instance(mod)
    _force_available(mod, monkeypatch, present=True)
    assert obj.available is True
    assert obj.reason is None


# ── G3: connectivity_check must never let an executor error escape (never 500) ─

def test_g3_connectivity_check_absorbs_executor_exception(monkeypatch):
    asset = _module("app.services.asset_service")
    from app.services.executors import CONNECTOR_SSH  # noqa: PLC0415

    class BoomExecutor:
        def check(self, host):  # noqa: ANN001
            raise RuntimeError("boom")

    fake_registry = SimpleNamespace(build_executor=lambda connector: BoomExecutor())
    monkeypatch.setattr(asset, "executor_registry", fake_registry)
    host = _mount_fake_host(asset, monkeypatch, CONNECTOR_SSH)
    fake_db = SimpleNamespace(commit=lambda: None)

    try:
        res = asset.connectivity_check(fake_db, None, 1)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            "connectivity_check must absorb executor errors (ssh probe must never "
            f"500); got {type(exc).__name__}: {exc}"
        )

    assert isinstance(res, dict)
    assert set(res) == _CHECK_KEYS, set(res)
    assert res["ok"] is False, res
    assert host.status == "offline", host.status


def test_g3b_connectivity_check_passes_through_degraded_dict(monkeypatch):
    asset = _module("app.services.asset_service")
    from app.services.executors import CONNECTOR_SSH  # noqa: PLC0415

    class DegradedExecutor:
        def check(self, host):  # noqa: ANN001
            return {"ok": False, "latency_ms": None, "detail": "ssh check not implemented"}

    fake_registry = SimpleNamespace(build_executor=lambda connector: DegradedExecutor())
    monkeypatch.setattr(asset, "executor_registry", fake_registry)
    host = _mount_fake_host(asset, monkeypatch, CONNECTOR_SSH)
    fake_db = SimpleNamespace(commit=lambda: None)

    res = asset.connectivity_check(fake_db, None, 1)
    assert set(res) == _CHECK_KEYS, set(res)
    assert res["ok"] is False, res
    assert res["latency_ms"] is None, res
    assert host.status == "offline", host.status
