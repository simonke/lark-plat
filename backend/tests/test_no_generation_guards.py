"""B1 guard: task_no / approval_no / ticket_no must be race-free sequence-backed.

Architect ruling: display numbers derive at view layer and must not depend on
the max(id)+1 window (collision-prone under concurrent creators). PostgreSQL
sequences are atomic, so both generators read nextval() only. These tests pin:
  - rapid interleaved calls yield no duplicates (per generator and combined)
  - exec _task_no uses seq_exec_no, exec/approval _approval_no use seq_approval_no
  - ticket _ticket_no uses seq_ticket_no (P3.1 tuple v1 @架构 seq2739)
  - output format stays YYYYMMDD-<n> / AP-YYYYMMDD-<n> / TK-YYYYMMDD-<n> (<= 32 chars)
"""

from __future__ import annotations

import re
import threading
from types import SimpleNamespace

import pytest

from app.services import approval_service, exec_service, ticket_service


class _SeqDb:
    def __init__(self, counters: dict[str, int]):
        self._counters = counters
        self._lock = threading.Lock()

    def execute(self, stmt):
        sql = str(stmt)
        name = sql.split("nextval('", 1)[1].split("'", 1)[0]
        with self._lock:
            n = self._counters[name] + 1
            self._counters[name] = n
        return SimpleNamespace(scalar=lambda: n)


def _collect(db, fn, results, n=400):
    for _ in range(n):
        results.append(fn(db))


def test_task_no_sequence_backed_race_free():
    db = _SeqDb({"seq_exec_no": 0})
    seen = {exec_service._task_no(db) for _ in range(2000)}
    assert len(seen) == 2000


def test_approval_no_generators_share_sequence_and_unique():
    db = _SeqDb({"seq_approval_no": 0})
    seen = {exec_service._approval_no(db) for _ in range(1000)}
    seen |= {approval_service._approval_no(db) for _ in range(1000)}
    assert len(seen) == 2000
    assert all(x.startswith("AP-") for x in seen)


def test_no_generators_use_distinct_sequences():
    exec_db = _SeqDb({"seq_exec_no": 0, "seq_approval_no": 0})
    task_db = _SeqDb({"seq_exec_no": 0})
    approval_db = _SeqDb({"seq_approval_no": 0})
    task_nos = {exec_service._task_no(task_db) for _ in range(50)}
    appr_nos = {exec_service._approval_no(exec_db) for _ in range(50)}
    assert task_nos.isdisjoint(appr_nos)
    # exec and approval generators draw from the same approval sequence.
    assert {exec_service._approval_no(exec_db) for _ in range(50)}.isdisjoint(
        {approval_service._approval_no(approval_db) for _ in range(50)})
    assert exec_db._counters["seq_exec_no"] == 0


def test_no_format_and_length_contract():
    db = _SeqDb({"seq_exec_no": 0, "seq_approval_no": 0})
    task_no = exec_service._task_no(db)
    approval_no = exec_service._approval_no(db)
    assert len(task_no) <= 32 and len(approval_no) <= 32
    head, _, suffix = task_no.rpartition("-")
    assert head.isdigit() and len(head) == 8 and suffix.isdigit()
    parts = approval_no.split("-")
    assert parts[0] == "AP" and parts[1].isdigit() and len(parts[1]) == 8 and parts[2].isdigit()


def test_task_no_concurrent_readers_no_duplicate():
    db = _SeqDb({"seq_exec_no": 0})
    results: list[str] = []
    threads = [threading.Thread(target=_collect, args=(db, exec_service._task_no, results))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 3200
    assert len(set(results)) == 3200


# ── P3.1 ticket_no (tuple v1 @架构 seq2739) ──────────────────────────────────

TICKET_NO_RE = re.compile(r"^TK-\d{8}-\d{3,}$")


class _RecordingDb:
    """Records every statement; returns an incrementing scalar for nextval()."""

    def __init__(self):
        self.statements: list[str] = []
        self._n = 0

    def _bump(self):
        self._n += 1
        return self._n

    def execute(self, stmt):
        sql = str(stmt)
        self.statements.append(sql)
        n = self._bump() if "nextval" in sql.lower() else 0
        return SimpleNamespace(scalar=lambda: n)

    def scalar(self, stmt):
        self.statements.append(str(stmt))
        return 0


def _ticket_no_gen():
    fn = getattr(ticket_service, "_ticket_no", None)
    if fn is None:
        pytest.fail("EXPECTED RED until P3.1 lands: ticket_service._ticket_no missing")
    return fn


def test_ticket_no_sequence_backed_race_free():
    gen = _ticket_no_gen()
    db = _SeqDb({"seq_ticket_no": 0})
    seen = {gen(db) for _ in range(1000)}
    assert len(seen) == 1000


def test_ticket_no_format_matches_tuple_v1():
    gen = _ticket_no_gen()
    db = _SeqDb({"seq_ticket_no": 0})
    for _ in range(5):
        no = gen(db)
        assert len(no) <= 32, no
        assert TICKET_NO_RE.match(no), no


def test_ticket_no_generation_is_sequence_not_maxid():
    gen = _ticket_no_gen()
    db = _RecordingDb()
    gen(db)
    joined = " ".join(db.statements).lower()
    assert "seq_ticket_no" in joined, (
        f"ticket_no must read nextval('seq_ticket_no'); got {db.statements!r}"
    )
    assert "max(" not in joined, (
        f"ticket_no must NOT use max()+1 (race-prone); got {db.statements!r}"
    )