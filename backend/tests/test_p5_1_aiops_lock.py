r"""P5.1 (E3 ingest guardrails + 422 JSON-safe handler) contract locks — @单元 lock-first, add-only.

Frozen contract: @架构 **P5.1 收尾 tuple v1.0** (seq3425) + @需求 **§29.14** (seq3423).
Base = release **M10 `34364cec2701739f206d636528824cc8ce9b8f18`** (master).

Pinned surface (tuple v1.0; scope ①②④⑤):
  ② 422 JSON-safe : `app.main.validation_error_handler` serializes `exc.errors()` via
                    `jsonable_encoder`; the envelope top-level `code==400` / `message` /
                    HTTP status 422 stay UNCHANGED. A `ctx` carrying a non-JSON object
                    (e.g. a bare `ValueError`) must produce a **422 JSON body**, never a
                    500. (only front-asserted envelope contract is `code==400` + 422)
  ④ E3 embed guard: `kb_ingestion` enforces a chunk cap (module default
                    `_MAX_EMBED_CHUNKS == 200`). Over-cap = GRACEFUL degradation:
                    embed the first N chunks, skip the rest + emit audit/log, and the
                    publish still SUCCEEDS (no raise / no 500, no new error code).
                    Within-cap behaviour is unchanged. NO new migration: single head
                    stays `f5a6b7c8d9e0`.
  ① (refactor) / ⑤ (FE) are guarded elsewhere (existing P5 lock / FE gates).

EXPECTED: clean **RED** until the P5.1 backend lands (add-only). Import-guarded so a run
reports assertion failures, not collection errors. Offline only (no live PG/Redis; no
migrations applied; no network).

Run (backend checkout, backend venv):
    python -m pytest tests/test_p5_1_aiops_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import pathlib
import re
import types

import pytest


_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_VERSIONS_DIR = _BACKEND / "alembic" / "versions"

_P5_REV = "f5a6b7c8d9e0"  # P5/P5.1 single head (M10); P5.1 adds NO migration
_P6_REV = "P6_REV"  # P6 advances the single head (descends from the P5 rev)


def _try(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return exc


def _require(mod: str):
    obj = _try(mod)
    if isinstance(obj, Exception):
        pytest.fail(f"P5.1 lock: `{mod}` unavailable: {obj!r}")
    return obj


# ── ② 422 handler JSON-safety ────────────────────────────────────────────────

def _main():
    return _require("app.main")


def test_e1_validation_handler_json_safe():
    """②: a RequestValidationError whose `ctx` holds a bare `ValueError` must be
    rendered as a **422 JSON body** (via `jsonable_encoder`), never a 500.

    Calling the handler directly reproduces the untrapped path: before the fix the
    handler json-dumps a `ValueError` => `TypeError` (=> 500). After the fix the
    `data` payload is JSON-safe and the envelope is unchanged.
    """
    from fastapi.exceptions import RequestValidationError  # noqa: PLC0415

    main = _main()
    exc = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "kind"),
                "msg": "value is not a valid kind",
                "input": "nonsense",
                "ctx": {"error": ValueError("boom")},
            }
        ]
    )
    try:
        resp = asyncio.run(main.validation_error_handler(None, exc))
    except TypeError as err:  # noqa: PERF203
        pytest.fail(
            "422 validation handler must serialise `exc.errors()` with "
            f"`jsonable_encoder` (JSON-safe `data`); raised {err!r}"
        )
    assert resp.status_code == 422, f"handler must keep status 422; got {resp.status_code}"
    body = json.loads(resp.body)  # must be JSON-decoded without error
    assert body.get("code") == 400, (
        f"envelope `code` must stay 400 (CODE_BAD_REQUEST); got {body.get('code')!r}"
    )
    assert body.get("message") == "parameter validation failed", (
        f"envelope `message` must be unchanged; got {body.get('message')!r}"
    )
    assert isinstance(body.get("data"), list) and body["data"], (
        f"envelope `data` must carry the (JSON-safe) validation errors; got {body.get('data')!r}"
    )
    json.dumps(body)  # the whole envelope must be JSON-serialisable


def test_e2_handler_uses_jsonable_encoder():
    """②: the JSON-safety must come from `jsonable_encoder` on the handler (named mechanism,
    tuple v1.0 §②), not from an unrelated crash guard."""
    main = _main()
    src = inspect.getsource(main.validation_error_handler)
    assert "jsonable_encoder" in src, (
        "`validation_error_handler` must wrap its payload with `jsonable_encoder` "
        "(tuple v1.0 §②); source did not reference it"
    )


# ── ④ E3 embed cost/limit guardrails ─────────────────────────────────────────

def _kb():
    return _require("app.services.kb_ingestion")


class _FakeQuery:
    def filter(self, *a, **k):  # noqa: ANN002,ANN003
        return self

    def delete(self, *a, **k):  # noqa: ANN002,ANN003
        return 0


class _FakeDB:
    def query(self, *a, **k):  # noqa: ANN002,ANN003
        return _FakeQuery()


class _SpyClient:
    """Records the exact chunk list handed to `embed`; returns one vector per chunk."""

    def __init__(self):
        self.calls: list[list[str]] = []

    def embed(self, texts):
        chunk_list = list(texts)
        self.calls.append(chunk_list)
        return [[0.0, 1.0] for _ in chunk_list]


class _SpyStore:
    """Captures the records handed to `upsert`."""

    def __init__(self):
        self.records: list[dict] = []

    def upsert(self, records):
        self.records = list(records)
        return len(self.records)


def _article(content: str, *, aid: int = 7, visibility: str = "private"):
    article = types.SimpleNamespace(id=aid, summary="", visibility=visibility)
    version = types.SimpleNamespace(content=content)
    return article, version


def _wire(monkeypatch, kb, client, store):
    monkeypatch.setattr(kb, "_client", lambda: client)
    monkeypatch.setattr(kb, "build_embedding_store", lambda db=None, value=None: store)


def _cap(kb):
    cap = getattr(kb, "_MAX_EMBED_CHUNKS", None)
    if cap is None:
        pytest.fail(
            "④ lock: `kb_ingestion._MAX_EMBED_CHUNKS` must exist (module chunk cap, "
            "default 200) to bound embed cost (tuple v1.0 §④)"
        )
    return cap


def test_d1_embed_cap_constant_default_200():
    """④: the chunk cap is a module constant `_MAX_EMBED_CHUNKS`, default 200."""
    kb = _kb()
    cap = getattr(kb, "_MAX_EMBED_CHUNKS", None)
    assert cap == 200, (
        f"`kb_ingestion._MAX_EMBED_CHUNKS` must default to 200; got {cap!r}"
    )


def test_d2_over_cap_is_graceful_and_truncates(monkeypatch, caplog):
    """④: over-cap content must NOT raise — embed only the first N chunks, skip the rest
    (with an audit/log line), and still return a successful upsert count (no 500)."""
    kb = _kb()
    cap = _cap(kb)  # RED now (constant missing)
    client, store = _SpyClient(), _SpyStore()
    _wire(monkeypatch, kb, client, store)

    content = "a" * (cap + 5)  # chunk_size=1 => cap+5 chunks (over the cap)
    article, version = _article(content)

    with caplog.at_level(logging.WARNING):
        written = kb.ingest_article(_FakeDB(), article, version, chunk_size=1)

    assert len(client.calls) == 1, f"embed must be called once; got {len(client.calls)}"
    embedded = client.calls[0]
    assert len(embedded) == cap, (
        f"over-cap embed must receive EXACTLY the first {cap} chunks; got {len(embedded)}"
    )
    assert len(store.records) == cap, (
        f"only {cap} chunks may be stored (rest skipped); got {len(store.records)}"
    )
    assert written == cap, f"publish must still succeed and return {cap}; got {written}"
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warned, (
        "over-cap truncation must emit a WARNING log line (audit trail); none captured"
    )


def test_d3_within_cap_behaviour_unchanged(monkeypatch):
    """④: at or below the cap, ALL chunks are embedded/stored (no false truncation)."""
    kb = _kb()
    cap = _cap(kb)  # RED now (constant missing)
    client, store = _SpyClient(), _SpyStore()
    _wire(monkeypatch, kb, client, store)

    n_chunks = max(1, cap - 1)
    article, version = _article("a" * n_chunks)  # chunk_size=1 => n_chunks (<= cap)

    written = kb.ingest_article(_FakeDB(), article, version, chunk_size=1)

    assert len(client.calls) == 1 and len(client.calls[0]) == n_chunks, (
        f"within-cap embed must receive all {n_chunks} chunks; got "
        f"{[len(c) for c in client.calls]}"
    )
    assert len(store.records) == n_chunks, (
        f"within-cap must store all {n_chunks} chunks; got {len(store.records)}"
    )
    assert written == n_chunks


def test_d4_no_new_migration_single_head():
    """④/cross-cut: P5.1 is add-only with NO migration. The single head is now the
    newest batch rev (P6), which still descends from the P5 rev — P5.1 added none."""
    revs: dict[str, str | None] = {}
    for p in _VERSIONS_DIR.glob("*.py"):
        txt = p.read_text(encoding="utf-8")
        m = re.search(r'^revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        d = re.search(r'^down_revision\s*=\s*["\']([^"\']+)["\']', txt, re.M)
        if m:
            revs[m.group(1)] = d.group(1) if d else None
    downs = {v for v in revs.values() if v}
    heads = sorted(r for r in revs if r not in downs)
    assert heads == [_P6_REV], (
        f"single head must be the newest batch rev {_P6_REV} (P5.1 added NO migration); "
        f"got {heads}"
    )
    assert revs[_P6_REV] == _P5_REV, (
        f"{_P6_REV} must descend directly from the P5.1 rev {_P5_REV}; "
        f"got parent {revs[_P6_REV]!r}"
    )


def test_d5_paths_at_least_167():
    """④/cross-cut: P5.1 did not change the contract (167). P6 raises the surface
    add-only; this stays a monotonic floor (exact count pinned by the P6 lock)."""
    main = _main()
    paths = main.app.openapi().get("paths", {})
    assert len(paths) >= 167, (
        f"paths must be >= 167 (P5.1 surface; P6 adds add-only); got {len(paths)}"
    )
