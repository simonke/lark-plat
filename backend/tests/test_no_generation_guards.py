"""B1 guard: task_no / approval_no must be race-free sequence-backed (P2).

Architect ruling: display numbers derive at view layer and must not depend on
the max(id)+1 window (collision-prone under concurrent creators). PostgreSQL
sequences are atomic, so both generators read nextval() only. These tests pin:
  - rapid interleaved calls yield no duplicates (per generator and combined)
  - exec _task_no uses seq_exec_no, exec/approval _approval_no use seq_approval_no
  - output format stays YYYYMMDD-<n> / AP-YYYYMMDD-<n> (<= 32 chars)
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

from app.services import approval_service, exec_service


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