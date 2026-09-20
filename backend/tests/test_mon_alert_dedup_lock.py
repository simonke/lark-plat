"""P2 close-out lock: mon_alert (rule, entity) active-row dedup + partial unique index.

Offline-only: the migration's SQL is exercised against an in-memory SQLite database
(PG JSONB ->> and SQLite JSON text ->> share the operator), so this lock never
touches the shared live DB. Covers the close-out acceptance points:
  - chain: single new head onto the P2-3 head c3d4e5f6a7b8;
  - dedup: historical duplicates collapse to the newest active row per group;
  - idempotence: re-running the dedup leaves the table unchanged;
  - uniqueness: the partial unique index blocks a second active (rule, entity) row;
  - rollback: the index can be dropped.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "e8a1b2c3d4f5_p2_closeout_mon_alert_dedup.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_p2_closeout_dedup", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


MIG = _load_migration()

_ROW = "(id INTEGER PRIMARY KEY, rule_id INTEGER, entity TEXT, status TEXT, resolved_at TEXT)"
_SEED = [
    (1, 10, '{"entity_id": "h1"}', "pending", None),
    (2, 10, '{"entity_id": "h1"}', "firing", None),
    (3, 10, '{"entity_id": "h1"}', "resolved", None),
    (4, 10, '{"entity_id": "h2"}', "pending", None),
    (5, None, '{"entity_id": "h3"}', "pending", None),
    (6, None, '{"entity_id": "h3"}', "pending", None),
    (7, 20, '{"entity_id": "h1"}', "acknowledged", None),
]


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute(f"CREATE TABLE mon_alert {_ROW}")
    conn.executemany("INSERT INTO mon_alert VALUES (?,?,?,?,?)", _SEED)
    return conn


def _status_map(conn) -> dict:
    return {row[0]: row[1] for row in conn.execute("SELECT id, status FROM mon_alert")}


def test_migration_chains_onto_p23_head():
    assert MIG.revision == "e8a1b2c3d4f5"
    assert MIG.down_revision == "c3d4e5f6a7b8"
    assert callable(MIG.upgrade) and callable(MIG.downgrade)


def test_dedup_keeps_newest_active_row_per_rule_entity():
    conn = _db()
    conn.execute(MIG.DEDUP_SQL)
    status = _status_map(conn)
    assert status == {1: "resolved", 2: "firing", 3: "resolved",
                      4: "pending", 5: "pending", 6: "pending", 7: "acknowledged"}
    # one active row per (rule_id, entity_id) among live rows
    active = conn.execute(
        "SELECT rule_id, entity, COUNT(*) FROM mon_alert "
        "WHERE status IN ('pending','firing','acknowledged') AND rule_id IS NOT NULL "
        "GROUP BY rule_id, entity"
    ).fetchall()
    assert all(count == 1 for _, _, count in active)
    # NULL rule_id rows are out of scope and untouched
    assert status[5] == "pending" and status[6] == "pending"


def test_dedup_is_idempotent():
    conn = _db()
    conn.execute(MIG.DEDUP_SQL)
    first = _status_map(conn)
    conn.execute(MIG.DEDUP_SQL)
    assert _status_map(conn) == first


def test_partial_unique_index_blocks_second_active_row():
    conn = _db()
    conn.execute(MIG.DEDUP_SQL)
    conn.execute(MIG.INDEX_SQL)
    try:
        conn.execute("INSERT INTO mon_alert VALUES (8, 10, '{\"entity_id\": \"h1\"}', 'pending', NULL)")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("partial unique index did not enforce active uniqueness")
    # a resolved duplicate and a different entity are both allowed
    conn.execute("INSERT INTO mon_alert VALUES (9, 10, '{\"entity_id\": \"h1\"}', 'resolved', NULL)")
    conn.execute("INSERT INTO mon_alert VALUES (10, 10, '{\"entity_id\": \"h9\"}', 'pending', NULL)")
    assert conn.execute("SELECT COUNT(*) FROM mon_alert").fetchone()[0] == 9


def test_downgrade_drops_index():
    conn = _db()
    conn.execute(MIG.DEDUP_SQL)
    conn.execute(MIG.INDEX_SQL)
    conn.execute(MIG.DROP_INDEX_SQL)
    conn.execute("INSERT INTO mon_alert VALUES (11, 10, '{\"entity_id\": \"h1\"}', 'pending', NULL)")
    assert conn.execute("SELECT COUNT(*) FROM mon_alert").fetchone()[0] == 8
