"""Lock: live 环境-代码契约（**静态侧**）。

随批 `p2ss-live-env-gates`（off master `6e8c353`）**add-only**。静态侧**不连 live、不断言 live 值**，
只固化可离线判定的契约（三集合 A/B/C，架构 seq2371；需求 seq2370）：

- **A `LIVE_REV_ALLOWED`** = `{d4e5f6a7b8c9, c3d4e5f6a7b8}` —— live `alembic_version` **合法性/允许停留值**
  （`code-required` 上界由 **B** 推导，见 @后端 seq2381；**A ≠ B，禁互换**）。
- **B `MIGRATION_LIVE_APPLICABLE`** = 11 版（`…→c3d4e5f6a7b8`，可被应用的迁移全集）。
- **C `MIGRATION_LIVE_FORBIDDEN`** = `{e8a1b2c3d4f5, c9e3f1a2b4d6, e1f2a3b4c5d7, f2a3b4c5d6e7}`（禁落共享库；close-out、P3、P3.x 与 P3.3 迁移含哨兵常量）。

断言（离线）：
- **S1 理由守卫**：close-out 迁移以**稳定哨兵常量** `SHARED_LIVE_DB_FORBIDDEN = True` 声明「禁落共享库」
  （**不**绑散文；`import` 迁移模块读**同一对象**，needs req seq2356-2）。
- **S2 完备性（用 B∪C，非 A∪C）**：`链 == B ∪ C`、`B ∩ C == ∅`、`15 == 11 + 4`（零空洞）、
  单头且 `head ∈ B ∪ C`（已分类）。
- **S3 可停留性（用 A）**：`A ⊆ B`，且 A 在链上**连续**（下界→上界紧邻）；close-out 紧邻 A 上界。
- **S4 常量入图**：A 成员 ∈ 迁移图（防拼写漂移）。

裁定依据：架构 seq2349/seq2353/seq2371、后端 seq2351/seq2369、需求 seq2352/2370/2373、reviewer seq2372。
**动态闸**（非本锁）：`code-required = max{链 ∩ B}`（**上界取 B**）`<= live ∈ A`（**非 `== head`**），
且须区分「**版本合法**（∈A）」与「**功能就绪**（代表触库路由非 5xx）」；未分类链版 ⇒ NOT RUN。

Run (from the backend checkout, backend venv):
    python -m pytest tests/test_live_env_contract_lock.py -p no:cacheprovider -o addopts= -q
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

# ── frozen contract constants (A = allowed dwell; B = applicable; C = forbidden) ──
# Source: backend seq2351/seq2369, arch seq2371; independently recomputed by unit.
LIVE_REV_ALLOWED = {"d4e5f6a7b8c9", "c3d4e5f6a7b8"}
MIGRATION_LIVE_APPLICABLE = {
    "e70f471cb518",
    "a1c7e9d24b60",
    "c4f7a1d20e91",
    "a7b3c5d9f2e1",
    "d1e2f3a4b5c6",
    "f5e010c0a100",
    "e6f7a8b9c0d1",
    "a1b2c3d4e5f6",
    "b2c3d4e5f6a7",
    "d4e5f6a7b8c9",
    "c3d4e5f6a7b8",
}
CLOSEOUT_REV = "e8a1b2c3d4f5"
# P3-1/P3-2 migration (descends from the close-out) -> also forbidden on shared live.
P3_REV = "c9e3f1a2b4d6"
# P3.x ticket_no migration (descends from the P3 head) -> also forbidden on shared live.
P3X_REV = "e1f2a3b4c5d7"
# P3-3 CMDB relation migration (descends from the P3.x head) -> also forbidden on shared live.
P3_3_REV = "f2a3b4c5d6e7"
MIGRATION_LIVE_FORBIDDEN = {CLOSEOUT_REV, P3_REV, P3X_REV, P3_3_REV}
SENTINEL_NAME = "SHARED_LIVE_DB_FORBIDDEN"


def _versions_dir() -> Path:
    import app  # noqa: PLC0415

    return Path(app.__file__).resolve().parent.parent / "alembic" / "versions"


def _revisions() -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for f in _versions_dir().glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        rev = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        down = re.search(r'^down_revision(?::[^=]+)?\s*=\s*(None|["\']([^"\']*)["\'])', text, re.M)
        if not rev:
            continue
        d = None
        if down:
            d = None if down.group(1) == "None" else down.group(2)
        out.append((rev.group(1), d))
    return out


def _migration_file(rev: str) -> Path | None:
    for f in _versions_dir().glob("*.py"):
        text = f.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'^revision(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if m and m.group(1) == rev:
            return f
    return None


# ── S1: rationale guard via stable sentinel constant (NOT prose) ─────────────

def test_s1_closeout_migration_declares_shared_db_forbidden_sentinel():
    # Import the migration module and read the SAME sentinel object (single source
    # of truth; no duplicated literal in the lock) — req seq2356-2.
    path = _migration_file(CLOSEOUT_REV)
    assert path is not None, f"close-out migration {CLOSEOUT_REV} not found"
    spec = importlib.util.spec_from_file_location("_p2_closeout_migration_under_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert getattr(mod, SENTINEL_NAME, None) is True, (
        f"close-out migration {CLOSEOUT_REV} MUST declare stable sentinel "
        f"`{SENTINEL_NAME} = True` (seq2353: do NOT bind to prose). "
        "If this migration is intentionally allowed on shared live, revisit the allowlist contract."
    )


def test_s1b_forbidden_set_exactly_closeout_p3_and_p3x_disjoint_from_allowed():
    assert MIGRATION_LIVE_FORBIDDEN == {CLOSEOUT_REV, P3_REV, P3X_REV, P3_3_REV}, (
        f"C must be exactly {{{CLOSEOUT_REV}, {P3_REV}, {P3X_REV}, {P3_3_REV}}}; "
        f"got {sorted(MIGRATION_LIVE_FORBIDDEN)}"
    )
    assert CLOSEOUT_REV not in LIVE_REV_ALLOWED, (
        f"{CLOSEOUT_REV} (close-out) MUST NOT be in A LIVE_REV_ALLOWED (seq2140)"
    )
    assert CLOSEOUT_REV not in MIGRATION_LIVE_APPLICABLE, (
        f"{CLOSEOUT_REV} (close-out) MUST NOT be in B MIGRATION_LIVE_APPLICABLE"
    )
    for rev, label in ((P3_REV, "P3"), (P3X_REV, "P3.x"), (P3_3_REV, "P3.3")):
        assert rev not in LIVE_REV_ALLOWED and rev not in MIGRATION_LIVE_APPLICABLE, (
            f"{rev} ({label}) MUST NOT be in A/B: it descends from the close-out and is "
            "forbidden on the shared live DB"
        )


# ── S2: completeness via B ∪ C (NOT A ∪ C) ───────────────────────────────────

def test_s2_sets_are_complete_and_disjoint():
    revs = _revisions()
    assert revs, "alembic revisions not found"
    chain = {r for r, _ in revs}
    assert MIGRATION_LIVE_APPLICABLE & MIGRATION_LIVE_FORBIDDEN == set(), (
        "B ∩ C must be empty (a migration cannot be both applicable and forbidden)"
    )
    assert chain == MIGRATION_LIVE_APPLICABLE | MIGRATION_LIVE_FORBIDDEN, (
        "completeness must use B ∪ C (NOT A ∪ C, which covers only 3/12 and would RED): "
        f"only-in-chain={sorted(chain - (MIGRATION_LIVE_APPLICABLE | MIGRATION_LIVE_FORBIDDEN))}, "
        f"only-in-classification={sorted((MIGRATION_LIVE_APPLICABLE | MIGRATION_LIVE_FORBIDDEN) - chain)}"
    )
    assert len(chain) == 15 and len(MIGRATION_LIVE_APPLICABLE) == 11 and len(MIGRATION_LIVE_FORBIDDEN) == 4, (
        f"15 == 11 + 4 expected; got chain={len(chain)}, B={len(MIGRATION_LIVE_APPLICABLE)}, "
        f"C={len(MIGRATION_LIVE_FORBIDDEN)}"
    )
    downs = {d for _, d in revs if d}
    heads = {r for r, _ in revs if r not in downs}
    assert len(heads) == 1, f"exactly one alembic head expected; got {sorted(heads)}"
    head = next(iter(heads))
    assert head in MIGRATION_LIVE_APPLICABLE | MIGRATION_LIVE_FORBIDDEN, (
        f"head {head!r} must be classified (∈ B ∪ C)"
    )


# ── S3: dwell set A ⊆ B and contiguous on the chain ─────────────────────────

def test_s3_allowed_set_subset_of_applicable_and_contiguous():
    by_rev = dict(_revisions())
    assert LIVE_REV_ALLOWED <= MIGRATION_LIVE_APPLICABLE, (
        f"A ⊆ B must hold; A-B={sorted(LIVE_REV_ALLOWED - MIGRATION_LIVE_APPLICABLE)}"
    )
    assert "d4e5f6a7b8c9" in by_rev and "c3d4e5f6a7b8" in by_rev, (
        "allowed members must exist in the migration graph"
    )
    assert by_rev["c3d4e5f6a7b8"] == "d4e5f6a7b8c9", (
        "allowed range must be contiguous: c3d4e5f6a7b8.down_revision == d4e5f6a7b8c9; "
        f"got {by_rev['c3d4e5f6a7b8']!r}"
    )
    assert by_rev.get(CLOSEOUT_REV) == "c3d4e5f6a7b8", (
        "close-out head must sit directly above the allowed upper bound; "
        f"got {by_rev.get(CLOSEOUT_REV)!r}"
    )


# ── S4: allowed members exist in the migration graph ────────────────────────

def test_s4_allowed_members_exist_in_graph():
    graph = {r for r, _ in _revisions()}
    missing = LIVE_REV_ALLOWED - graph
    assert not missing, f"LIVE_REV_ALLOWED members not in migration graph: {sorted(missing)}"
