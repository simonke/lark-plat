"""Live readiness smoke gate for lark-plat (stdlib only).

Runs the three checks a live batch must pass before live evidence is accepted:

  1. contract   : live /openapi.json is JSON-equal to the repo docs/openapi.json
                  of the tree that is believed to be served;
  2. db_rev     : live PostgreSQL alembic_version is inside the shared-DB
                  allow-list AND satisfies 'code-required <= live <= upper';
  3. db_touch   : one representative DB-touching route answers with a non-5xx
                  status (transport failure is NOT RUN, HTTP >= 500 is BLOCKED).

Output lines are PASS / BLOCKED / NOT RUN. Exit code 0 only when nothing is BLOCKED
and nothing is NOT RUN for the required checks.

The allow-list mirrors docs/migration-shared-db-allowlist.md and must stay in
sync with the static lock and docs/migration-shared-db-allowlist.md
(A = LIVE_REV_ALLOWED, B = MIGRATION_LIVE_APPLICABLE, C = MIGRATION_LIVE_FORBIDDEN).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# A: live alembic_version values the shared DB is allowed to stay at (upper bound).
LIVE_REV_ALLOWED = {"d4e5f6a7b8c9", "c3d4e5f6a7b8"}
# B: migrations allowed to be applied to the shared DB (chain up to the upper bound).
MIGRATION_LIVE_APPLICABLE = {
    "e70f471cb518", "a1c7e9d24b60", "c4f7a1d20e91", "a7b3c5d9f2e1",
    "d1e2f3a4b5c6", "f5e010c0a100", "e6f7a8b9c0d1", "a1b2c3d4e5f6",
    "b2c3d4e5f6a7", "d4e5f6a7b8c9", "c3d4e5f6a7b8",
}
# C: migrations forbidden on the shared DB (P2 close-out + P3 ticket/kb + P3.x
# ticket_no, which descend from the close-out and therefore cannot be applied
# to shared live).
MIGRATION_LIVE_FORBIDDEN = {"e8a1b2c3d4f5", "c9e3f1a2b4d6", "e1f2a3b4c5d7"}
TOUCH_ROUTE = "/auth/providers"

PASS, BLOCKED, NOT_RUN = "PASS", "BLOCKED", "NOT RUN"


def _repo_root(arg: str | None) -> Path:
    if arg:
        return Path(arg).resolve()
    return Path(__file__).resolve().parents[2]


def _migration_order(versions_dir: Path) -> list[str]:
    revs: dict[str, str | None] = {}
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r"^revision(?:\s*:\s*[^=\n]+)?\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        down = re.search(
            r"^down_revision(?:\s*:\s*[^=\n]+)?\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", text, re.M)
        if rev:
            revs[rev.group(1)] = down.group(1) if down and down.group(1) else None
    ordered: list[str] = []
    child = {down: rev for rev, down in revs.items()}
    start = next((r for r, d in revs.items() if d is None), None)
    while start:
        ordered.append(start)
        start = child.get(start)
    return ordered


def _http_json(url: str) -> tuple[int, object]:
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _dsn(repo: Path, arg: str | None) -> str | None:
    if arg:
        return arg
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    env_file = repo / "backend" / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    return None


def _check_contract(api_base: str, repo: Path) -> tuple[str, str]:
    root = api_base[:-len("/api/v1")] if api_base.endswith("/api/v1") else api_base
    docs = repo / "docs" / "openapi.json"
    try:
        _, live = _http_json(root.rstrip("/") + "/openapi.json")
    except Exception as exc:  # noqa: BLE001
        return NOT_RUN, f"live openapi unreachable: {exc}"
    if not docs.is_file():
        return NOT_RUN, f"repo contract missing: {docs}"
    served = json.loads(docs.read_text(encoding="utf-8"))
    if live == served:
        return PASS, "live /openapi.json == repo docs/openapi.json"
    return BLOCKED, "live /openapi.json differs from repo docs/openapi.json"


def _check_db_rev(repo: Path, dsn: str | None, code_required: str | None) -> tuple[str, str]:
    if not dsn:
        return NOT_RUN, "no DATABASE_URL/.env dsn"
    try:
        import psycopg2  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return NOT_RUN, f"psycopg2 unavailable: {exc}"
    try:
        conn = psycopg2.connect(re.sub(r"\+[a-z0-9_]+://", "://", dsn, count=1))
        cur = conn.cursor()
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        return NOT_RUN, f"db query failed: {exc}"
    if not row:
        return BLOCKED, "alembic_version empty"
    live = row[0]
    order = _migration_order(repo / "backend" / "alembic" / "versions")
    unclassified = [
        rev for rev in order
        if rev not in MIGRATION_LIVE_APPLICABLE and rev not in MIGRATION_LIVE_FORBIDDEN
    ]
    if unclassified:
        return NOT_RUN, f"unclassified chain rev(s): {unclassified} (never PASS)"
    required = code_required or next(
        (rev for rev in reversed(order) if rev in MIGRATION_LIVE_APPLICABLE), None)
    if not required:
        return NOT_RUN, "code-required undetermined; pass --code-required (never PASS)"
    if live in MIGRATION_LIVE_FORBIDDEN:
        return BLOCKED, f"live rev {live} is forbidden on the shared DB"
    if live not in LIVE_REV_ALLOWED:
        return BLOCKED, f"live rev {live} not in allow-list {sorted(LIVE_REV_ALLOWED)}"
    if required not in order or live not in order:
        return NOT_RUN, f"rev not on repo chain (live={live}, required={required})"
    if order.index(live) < order.index(required):
        return BLOCKED, f"code requires {required} but live is {live}"
    return PASS, f"live rev {live} >= code-required {required} (allow-list ok)"


def _check_db_touch(api_base: str) -> tuple[str, str]:
    try:
        status = _http_status(api_base.rstrip("/") + TOUCH_ROUTE)
    except Exception as exc:  # noqa: BLE001
        return NOT_RUN, f"transport error: {exc}"
    if status >= 500:
        return BLOCKED, f"GET {TOUCH_ROUTE} -> HTTP {status}"
    return PASS, f"GET {TOUCH_ROUTE} -> HTTP {status} (non-5xx)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="live readiness smoke gate")
    parser.add_argument("--api-base", default=os.environ.get(
        "LARK_PLAT_API_BASE", "http://127.0.0.1:8000/api/v1"))
    parser.add_argument("--repo", default=None)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--code-required", default=None,
                        help="revision the served code requires on the shared DB; "
                             "defaults to the highest live-applicable (B) rev present "
                             "in the repo migration chain (never silently PASS)")
    args = parser.parse_args(argv)

    repo = _repo_root(args.repo)
    dsn = _dsn(repo, args.dsn)

    results = {
        "contract": _check_contract(args.api_base, repo),
        "db_rev": _check_db_rev(repo, dsn, args.code_required),
        "db_touch": _check_db_touch(args.api_base),
    }
    for name, (verdict, detail) in results.items():
        print(f"{name:9s} {verdict:8s} {detail}")

    blocked = [n for n, (v, _) in results.items() if v == BLOCKED]
    not_run = [n for n, (v, _) in results.items() if v == NOT_RUN]
    if blocked:
        print(f"RESULT: BLOCKED ({', '.join(blocked)})")
        return 1
    if not_run:
        print(f"RESULT: NOT RUN ({', '.join(not_run)})")
        return 2
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
