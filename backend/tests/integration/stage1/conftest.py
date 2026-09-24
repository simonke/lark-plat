"""Shared fixtures for the lark-plat stage-1 integration harness.

Committed add-only into the repo (架构 seq2140 item4) from the authoring seat
`work/stage1-integration` (集成测试工程师). This subtree is self-contained: it
does not import the backend app except for the source-level 差异A assertion, and
it does not touch the shared DB unless live tests are explicitly enabled.

Environment:
    LARK_PLAT_API_BASE  API base URL, e.g. http://localhost:8000/api/v1.
                        **Setting this variable is what enables `live` tests** —
                        with it unset, every `live`/`seed` test skips, so a plain
                        `pytest` run in CI/local stays offline and deterministic.
    OPENAPI_PATH        path to the committed openapi.json for static checks
                        (default: stage1/fixtures/openapi.json)
    LARK_PLAT_REPO      repo root override for the 差异A source assertion
    ADMIN/OPERATOR/VIEWER creds: default admin/admin@larkplat, operator/operator_pwd,
                        viewer/viewer_pwd (seed fixture, per module-design §12)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

DEFAULT_CRE = {
    "admin": ("admin", "admin@larkplat"),
    "operator": ("operator", "operator_pwd"),
    "viewer": ("viewer", "viewer_pwd"),
}

_HERE = Path(__file__).resolve().parent

# Gate-safe default: live tests are OFF unless LARK_PLAT_API_BASE is set. This
# keeps a plain `pytest` run (CI / backend unit gate) fully offline even on a
# developer box that happens to have a backend on :8000.
API_BASE = os.environ.get("LARK_PLAT_API_BASE", "http://localhost:8000/api/v1")
LIVE_ENABLED = "LARK_PLAT_API_BASE" in os.environ

_OPENAPI_DEFAULT = os.environ.get("OPENAPI_PATH", str(_HERE / "fixtures" / "openapi.json"))

# backend/ = parents[2] (stage1 -> integration -> tests -> backend)
_BACKEND = _HERE.parents[2]
_REPO_ROOTS = [
    os.environ.get("LARK_PLAT_REPO", ""),
    str(_BACKEND.parent),
]


def _discover_openapi() -> Path:
    p = Path(_OPENAPI_DEFAULT)
    if p.is_file():
        return p
    if (_HERE / "fixtures" / "openapi.json").is_file():
        return _HERE / "fixtures" / "openapi.json"
    raise FileNotFoundError(
        f"openapi.json not found at {p}; copy the stage-1 snapshot into "
        "integration/stage1/fixtures/openapi.json or set OPENAPI_PATH"
    )


@pytest.fixture(scope="session")
def api_base() -> str:
    return API_BASE


@pytest.fixture(scope="session")
def openapi_spec() -> dict:
    with _discover_openapi().open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def auth_service_source():
    """Committed backend/app/services/auth_service.py (差异A source-level assert).

    Skips if no lark-plat backend checkout is configured/discovered.
    """
    for root in _REPO_ROOTS:
        if not root:
            continue
        path = Path(root) / "backend" / "app" / "services" / "auth_service.py"
        if path.is_file():
            return path.read_text(encoding="utf-8")
    pytest.skip("auth_service.py not found; set LARK_PLAT_REPO to the lark-plat checkout")


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=30.0)


_REACHABILITY: dict = {"checked": False, "ok": False}


def _api_reachable(client: httpx.Client) -> bool:
    if not LIVE_ENABLED:
        return False
    if _REACHABILITY["checked"]:
        return _REACHABILITY["ok"]
    _REACHABILITY["checked"] = True
    try:
        client.post("/auth/login", json={"username": "_probe", "password": "_probe"})
        _REACHABILITY["ok"] = True
    except httpx.HTTPError:
        _REACHABILITY["ok"] = False
    return _REACHABILITY["ok"]


def _skip_live() -> None:
    if not LIVE_ENABLED:
        pytest.skip(
            "live NOT RUN — LARK_PLAT_API_BASE unset (offline gate-safe default; "
            "not run, therefore not a pass)"
        )
    pytest.skip(
        f"live NOT RUN — transport error / API unreachable at {API_BASE} "
        "(not run, therefore not a pass)"
    )


def _fail_on_server_error(resp: httpx.Response, where: str) -> None:
    """A reachable server returning 5xx is an environment/code defect (e.g. DB
    schema drift), NOT "unreachable" — surface it as a failure so the live gate
    cannot silently turn green. Only transport errors may skip (see _skip_live).

    backend seq2344; architect seq2349 (owner: 后端).
    """
    if resp.status_code >= 500:
        pytest.fail(
            f"live server error HTTP {resp.status_code} on {where} ({API_BASE}); "
            f"body={resp.text[:300]!r}",
            pytrace=False,
        )


@pytest.fixture(scope="session")
def api_ready(client) -> None:
    if not _api_reachable(client):
        _skip_live()


@pytest.fixture(autouse=True)
def _gate_live_tests(request, client):
    if request.node.get_closest_marker("live"):
        if not _api_reachable(client):
            _skip_live()


@pytest.fixture(scope="session")
def login(client: httpx.Client):
    """Returns a login helper; skips (NOT RUN) when live is disabled, fails on 5xx.

    Session-scoped, so it is set up before the function-scoped `_gate_live_tests`
    autouse gate; it must therefore consult LIVE_ENABLED itself to keep a plain
    `pytest` run fully offline/deterministic (no accidental :8000 contact).
    """
    if not LIVE_ENABLED:
        _skip_live()

    def _login(username: str, password: str) -> httpx.Response:
        try:
            resp = client.post("/auth/login", json={"username": username, "password": password})
        except httpx.HTTPError:
            _skip_live()
        _fail_on_server_error(resp, "POST /auth/login")
        if resp.status_code == 404:
            pytest.skip(f"auth/login not routed ({resp.status_code})")
        return resp
    return _login


@pytest.fixture(scope="session")
def creds() -> dict:
    return {
        role: (
            os.environ.get(f"LARK_{role.upper()}_USER", u),
            os.environ.get(f"LARK_{role.upper()}_PWD", p),
        )
        for role, (u, p) in DEFAULT_CRE.items()
    }


@pytest.fixture(scope="session")
def tokens(login, creds) -> dict[str, dict]:
    """One access token per seed role. Requires seed data (module-design §12)."""
    out: dict[str, dict] = {}
    for role, (user, pwd) in creds.items():
        resp = login(user, pwd)
        _fail_on_server_error(resp, f"POST /auth/login ({role})")
        if resp.status_code != 200:
            pytest.skip(
                f"seed login failed for {role} ({user}): HTTP {resp.status_code} — "
                "seed data not loaded yet (backend stage-1 落库 pending)"
            )
        body = resp.json()
        out[role] = {
            "access_token": body["data"]["access_token"],
            "refresh_token": body["data"]["refresh_token"],
            "username": user,
        }
    return out


@pytest.fixture(scope="session")
def auth_headers(tokens):
    def _headers(role: str) -> dict:
        return {"Authorization": f"Bearer {tokens[role]['access_token']}"}
    return _headers
