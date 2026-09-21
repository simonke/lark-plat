"""Live readiness smoke gate for lark-plat (stdlib only).

Runs the three checks a live batch must pass before live evidence is accepted:

  1. contract   : live /openapi.json is JSON-equal to the repo docs/openapi.json
                  of the tree that is believed to be served;
  2. db_rev     : live PostgreSQL alembic_version is inside the shared-DB
                  allow-list AND satisfies 'code-required <= live <= upper';
  3. db_touch   : one representative DB-touching route answers with a non-5xx
                  status (transport failure is NOT RUN, HTTP >= 500 is FAIL).

Output lines are PASS / FAIL / NOT RUN. Exit code 0 only when nothing FAILs
and nothing is NOT RUN for the required checks.

The allow-list mirrors docs/migration-shared-db-allowlist.md and must stay in
sync with the static lock (ALLOWED_LIVE_REVS).
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

ALLOWED_LIVE_REVS = {"d4e5f6a7b8c9", "c3d4e5f6a7b8"}
FORBIDDEN_REVS = {"e8a1b2c3d4f5"}
TOUCH_ROUTE = "/auth/providers"

PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT RUN"


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
    return FAIL, "live /openapi.json differs from repo docs/openapi.json"


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
        return FAIL, "alembic_version empty"
    live = row[0]
    if live in FORBIDDEN_REVS:
        return FAIL, f"live rev {live} is forbidden on the shared DB"
    if live not in ALLOWED_LIVE_REVS:
        return FAIL, f"live rev {live} not in allow-list {sorted(ALLOWED_LIVE_REVS)}"
    if code_required:
        order = _migration_order(repo / "backend" / "alembic" / "versions")
        if code_required in order and live in order and order.index(live) < order.index(code_required):
            return FAIL, f"code requires {code_required} but live is {live}"
    return PASS, f"live rev {live} (allow-list ok)"


def _check_db_touch(api_base: str) -> tuple[str, str]:
    try:
        status = _http_status(api_base.rstrip("/") + TOUCH_ROUTE)
    except Exception as exc:  # noqa: BLE001
        return NOT_RUN, f"transport error: {exc}"
    if status >= 500:
        return FAIL, f"GET {TOUCH_ROUTE} -> HTTP {status}"
    return PASS, f"GET {TOUCH_ROUTE} -> HTTP {status} (non-5xx)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="live readiness smoke gate")
    parser.add_argument("--api-base", default=os.environ.get(
        "LARK_PLAT_API_BASE", "http://127.0.0.1:8000/api/v1"))
    parser.add_argument("--repo", default=None)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--code-required", default=None,
                        help="revision the served code requires on the shared DB")
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

    failed = [n for n, (v, _) in results.items() if v == FAIL]
    not_run = [n for n, (v, _) in results.items() if v == NOT_RUN]
    if failed:
        print(f"RESULT: FAIL ({', '.join(failed)})")
        return 1
    if not_run:
        print(f"RESULT: NOT RUN ({', '.join(not_run)})")
        return 2
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
