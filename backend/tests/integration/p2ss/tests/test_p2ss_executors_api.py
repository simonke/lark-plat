"""P2-SS executor-extension API-level integration tests (add-only).

Contract frozen at 架构 seq2185 / 需求 SS-1..6 (seq2186). Runs fully offline via
the harness in ``conftest.py`` (in-process app, SQLite, fake principal) — no
shared DB, no Redis, no real SSH.

Covered:
  * SS-2 add-only contract: ``GET .../executors`` + ``PUT .../connector``;
    ``docs/openapi.json`` paths == 109, ``/monitor*`` == 19.
  * SS-3 permission: success with ``asset:host:edit``, 403 without; zero
    credential echo in the response.
  * SS-4 connector switch persists; invalid connector value -> 422.

Deliberately NOT covered here (deferred, registered as a limitation): real SSH,
``paramiko`` install, ``agent.exe`` — all post-batch (D: drive).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

_EXECUTORS_PATH = "/api/v1/assets/hosts/{id}/executors"
_CONNECTOR_PATH = "/api/v1/assets/hosts/{id}/connector"

def _resolve_backend() -> Path:
    """Resolve the backend checkout hermetically.

    Order: explicit ``LARK_BACKEND`` override -> walk up to the checkout that
    owns ``app/main.py``. There is deliberately no machine-specific absolute
    fallback: one made the openapi-count assertion read an unrelated checkout's
    ``docs/openapi.json`` (non-hermetic; G2, seq2441).
    """
    env = os.environ.get("LARK_BACKEND")
    if env:
        return Path(env)
    for cand in Path(__file__).resolve().parents:
        if (cand / "app" / "main.py").is_file():
            return cand
    raise RuntimeError("LARK_BACKEND unset and no app/main.py found in parents")


_BACKEND = _resolve_backend()
_REPO_ROOT = _BACKEND.parent


def _route_names(app) -> set[str]:
    """Effective route names.

    This FastAPI wraps included routers in ``_IncludedRouter`` (so ``app.routes``
    holds wrapper objects, not ``APIRoute`` paths); use
    ``effective_route_contexts()`` when present.
    """
    names: set[str] = set()
    for r in app.routes:
        ec = getattr(r, "effective_route_contexts", None)
        if callable(ec):
            for ctx in ec():
                orig = getattr(ctx, "original_route", None)
                n = getattr(orig, "name", None)
                if n:
                    names.add(n)
        else:
            n = getattr(r, "name", None)
            if n:
                names.add(n)
    return names


@pytest.fixture(autouse=True)
def _require_p2ss_routes(app_client):
    client, _set_user, _seed_host = app_client
    names = _route_names(client.app)
    if not {"host_executors", "update_connector"} <= names:
        pytest.skip("P2-SS routes not present yet (pre-p2-ss-executor tree)")


# --------------------------------------------------------------------- SS-2

def test_executors_ok_shape(app_client):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1, connector="agent")
    resp = client.get(_EXECUTORS_PATH.format(id=hid))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert "available" in data and "active" in data and "reason" in data
    assert "agent" in data["available"]


def test_executors_403_without_perm(app_client):
    client, set_user, seed_host = app_client
    set_user(perms=set())
    hid = seed_host(1)
    resp = client.get(_EXECUTORS_PATH.format(id=hid))
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == 403


def _fake_ssh(*, available, reason=None):
    class _SSH:
        name = "ssh"

        def __init__(self):
            self.available = available
            self.reason = reason

        def check(self, host):
            return {"ok": available, "latency_ms": None, "detail": "fake"}

        def exec(self, *a, **k):
            raise NotImplementedError("fake")

    return _SSH()


def _patch_ssh(monkeypatch, *, available, reason=None):
    """Drive the frozen seam (module-attribute ``build_executor``), not the
    private ``_load_paramiko`` (架构 seq2210 / reviewer seq2211)."""
    import app.services.executors as registry

    real = registry.build_executor

    def fake_build(name):
        return _fake_ssh(available=available, reason=reason) if name == "ssh" else real(name)

    monkeypatch.setattr(registry, "build_executor", fake_build)


def test_executors_ssh_unavailable_reason(app_client, monkeypatch):
    """SS-1: with ssh unavailable, an ssh host is active but degraded with the
    exact reason while agent stays available (injected via the frozen seam)."""
    client, set_user, seed_host = app_client
    _patch_ssh(monkeypatch, available=False, reason="paramiko not installed")
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1, connector="ssh")
    data = client.get(_EXECUTORS_PATH.format(id=hid)).json()["data"]
    assert "agent" in data["available"]
    assert "ssh" not in data["available"]
    assert data["active"] == "ssh"
    assert data["reason"] == "paramiko not installed"


def test_executors_ssh_available_state(app_client, monkeypatch):
    """SS-1: when the optional dep is present the ssh executor reports available."""
    client, set_user, seed_host = app_client
    _patch_ssh(monkeypatch, available=True, reason=None)
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1, connector="ssh")
    data = client.get(_EXECUTORS_PATH.format(id=hid)).json()["data"]
    assert "agent" in data["available"] and "ssh" in data["available"]
    assert data["active"] == "ssh"
    assert data["reason"] is None


def test_executors_no_credential_echo(app_client, session):
    """SS-3: the response must not leak credential material."""
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1)

    from app.db.models import HostCredential

    session.add(
        HostCredential(
            id=99,
            host_id=hid,
            type="password",
            username="root",
            secret_enc="v1:SUPERSECRETCIPHER",
            key_version=1,
        )
    )
    session.commit()

    resp = client.get(_EXECUTORS_PATH.format(id=hid))
    assert resp.status_code == 200, resp.text
    assert "SUPERSECRETCIPHER" not in resp.text
    assert "secret_enc" not in resp.text


# --------------------------------------------------------------------- SS-4

def test_connector_switch_persists(app_client, session):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1, connector="agent")

    resp = client.put(_CONNECTOR_PATH.format(id=hid), json={"connector": "ssh"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["code"] == 0

    session.expire_all()
    from app.db.models import Host

    assert session.get(Host, hid).connector == "ssh"


def test_connector_invalid_value_422(app_client):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})
    hid = seed_host(1)
    resp = client.put(_CONNECTOR_PATH.format(id=hid), json={"connector": "telnet"})
    assert resp.status_code == 422, resp.text


def test_connector_403_without_perm(app_client):
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:list"})
    hid = seed_host(1)
    resp = client.put(_CONNECTOR_PATH.format(id=hid), json={"connector": "ssh"})
    assert resp.status_code == 403, resp.text


# -------------------------------------------------- gate parity (SS-5, HTTP面)

def test_executors_data_permission_gate_parity(app_client):
    """Both new endpoints enforce the same data-permission gate as the existing
    asset surface: an invisible host is 403 even with the permission code."""
    client, set_user, seed_host = app_client
    set_user(perms={"asset:host:edit"})  # visible_group_ids == [1]
    hid = seed_host(1, group_id=2)  # different group -> not visible

    r1 = client.get(_EXECUTORS_PATH.format(id=hid))
    assert r1.status_code == 403, r1.text
    r2 = client.put(_CONNECTOR_PATH.format(id=hid), json={"connector": "ssh"})
    assert r2.status_code == 403, r2.text


# ------------------------------------------------------------------ static

def test_openapi_path_count_and_monitor_stable():
    spec_path = _REPO_ROOT / "docs" / "openapi.json"
    if not spec_path.is_file():
        pytest.skip(f"openapi.json not found at {spec_path}")
    paths = json.loads(spec_path.read_text(encoding="utf-8"))["paths"]
    assert len(paths) == 109, f"expected 109 paths, got {len(paths)}"
    assert sum(1 for p in paths if "monitor" in p) == 19
    assert any(p.endswith("/executors") for p in paths), "executors path missing"
    assert any(p.endswith("/connector") for p in paths), "connector path missing"
