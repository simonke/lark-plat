"""Unit tests for WS hello-frame auto-bind (stage2 plan A, acceptance gap ④).

_bind_host must write host.agent_id back when exactly one unbound pre-registered
host matches the hello payload hostname/ip; first-bind-wins; ambiguous,
already-bound, or empty-payload cases are no-ops.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.ws import agent_ws


def make_host(hid=1, hostname="web-01", ip="10.0.0.1", agent_id=None):
    return SimpleNamespace(id=hid, hostname=hostname, ip=ip, agent_id=agent_id)


class FakeDb:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True

    def close(self):
        pass


def run_bind(monkeypatch, rows, agent_id="agt-x", data=None):
    db = FakeDb()

    class Repo:
        def __init__(self, _db):
            pass

        def list_all(self):
            return list(rows)

    monkeypatch.setattr(agent_ws, "SessionLocal", lambda: db)
    monkeypatch.setattr(agent_ws, "HostRepository", Repo)
    agent_ws._bind_host(agent_id, data or {"hostname": "web-01", "ip": "10.0.0.1"})
    return db


def test_binds_single_unbound_match_and_commits(monkeypatch):
    host = make_host()
    other = make_host(hid=2, hostname="db-01", ip="10.0.0.2")
    db = run_bind(monkeypatch, [other, host])
    assert host.agent_id == "agt-x"
    assert other.agent_id is None
    assert db.committed


def test_first_bind_wins_skips_when_agent_id_taken(monkeypatch):
    host = make_host(agent_id="agt-x")
    db = run_bind(monkeypatch, [host])
    assert host.agent_id == "agt-x"
    assert not db.committed


def test_no_matching_host_is_noop(monkeypatch):
    host = make_host(ip="9.9.9.9", hostname="nope")
    db = run_bind(monkeypatch, [host])
    assert host.agent_id is None
    assert not db.committed


def test_bound_candidate_excluded_from_matching(monkeypatch):
    bound = make_host(hid=3, agent_id="agt-other")
    db = run_bind(monkeypatch, [bound])
    assert bound.agent_id == "agt-other"
    assert not db.committed


def test_ambiguous_two_candidates_refused(monkeypatch):
    a = make_host(hid=1)
    b = make_host(hid=2)
    db = run_bind(monkeypatch, [a, b])
    assert a.agent_id is None and b.agent_id is None
    assert not db.committed


def test_empty_payload_short_circuits_without_db():
    agent_ws._bind_host("agt-x", {"hostname": "", "ip": ""})
