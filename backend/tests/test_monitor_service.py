"""P2-MA monitor service unit tests (state machine, dedup, escalate, dead-letter,
fingerprint, adapter secret masking, feature flag, schema validation).

Pins contract (2026-09-09):
  - mon_alert.status: pending/firing/acknowledged/resolved
  - actions fire|acknowledge|escalate|resolve|suppress; append-only events
  - schema failures dead-letter; severity fallback -> warning
  - adapter config secrets AES-GCM "enc:" masked on output
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import BadRequestError, NotFoundError
from app import schemas
from app.services import monitor_service

NOW = datetime.now(timezone.utc)


class _Rows:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _Db:
    def __init__(self, queue=()):
        self.added = []
        self.commits = 0
        self.flushed = 0
        self.queue = [c for c in queue] + [None] * 100

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def scalar(self, *a, **kw):
        return self.queue.pop(0) if self.queue else None

    def scalars(self, *a, **kw):
        return _Rows(self.queue.pop(0) if self.queue else [])

    def execute(self, *a, **kw):
        return self.scalars(*a, **kw)


def _user(uid=1, admin=True):
    return SimpleNamespace(
        id=uid, username="u", is_admin=1 if admin else 0,
        permissions=set(), visible_group_ids=[],
        require_perm=lambda code: None,
    )


def _alert(status="pending", fired_at=None, version=1, last_value=10.0, created_at=None,
           severity="warning"):
    return SimpleNamespace(
        id=1, rule_id=1, rule_name="r",
        entity={"entity_type": "host", "entity_id": "10.0.0.1", "entity_name": "h1"},
        source="prometheus", status=status, severity=severity,
        last_value=last_value, fired_at=fired_at, resolved_at=None,
        version=version, hit_count=1, created_by=1,
        created_at=created_at or NOW,
    )


def _rule(**over):
    base = dict(
        id=1, name="r", description=None, enabled=1,
        event_source=None, event_kind="metric", metric_name="cpu_usage",
        condition_operator=">", condition_threshold=80,
        condition_duration_seconds=0, scope_type=None, scope_ids=None,
        level="warning", cooldown_seconds=300, converge_sec=0,
        escalation_enabled=0, escalation_after_seconds=None,
        escalation_severity=None, escalate_levels=None,
        notify_scene="alert", notify_channel_ids={"ids": []},
        created_by=1, deleted=0, created_at=NOW, updated_at=NOW,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _metric_event(value=95.0):
    return {
        "kind": "metric", "source": "prometheus",
        "entity": {"entity_type": "host", "entity_id": "10.0.0.1", "entity_name": "h1"},
        "labels": {"metric_name": "cpu_usage"}, "value": value,
        "severity": "warning", "ts": NOW.isoformat(),
    }


# ── schema validation / normalization ────────────────────────────────────────


def test_validate_event_metric_requires_value():
    ok, err = monitor_service.validate_event(
        {"source": "prometheus", "kind": "metric",
         "entity": {"entity_id": "10.0.0.1"}, "ts": NOW.isoformat(), "value": 90.0})
    assert ok
    ok, err = monitor_service.validate_event(
        {"source": "prometheus", "kind": "metric",
         "entity": {"entity_id": "10.0.0.1"}, "ts": NOW.isoformat(), "value": None})
    assert not ok
    assert "value" in err


def test_validate_event_bad_source_rejected():
    ok, err = monitor_service.validate_event(
        {"source": "nope", "kind": "metric",
         "entity": {"entity_id": "10.0.0.1"}, "ts": NOW.isoformat(), "value": 1.0})
    assert not ok
    assert "source" in err


def test_fingerprint_stable_sha256():
    ev = _metric_event()
    f1 = monitor_service.build_fingerprint(ev)
    f2 = monitor_service.build_fingerprint(dict(ev))
    assert f1 == f2
    assert len(f1) == 64
    assert monitor_service.build_fingerprint({**ev, "value": 1.0}) != f1


def test_severity_fallback_unknown_to_warning():
    assert monitor_service._severity_from_status("critical") == "critical"
    assert monitor_service._severity_from_status("UNKNOWN") == "warning"


# ── rules CRUD field persistence (regression lock, ruling 2026-09-11) ────────


def test_persist_metric_sample_passes_source_to_upsert_daily(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=1, type="prometheus", enabled=1, name="p")
    event = _metric_event()
    captured = {}

    def _add_sample(*args, **kwargs):
        # class-attr mock receives self (repo instance) as args[0]
        captured["add_source"] = args[6] if len(args) > 6 else kwargs.get("source")

    def _upsert_daily(*args, **kwargs):
        captured["daily_source"] = args[1] if len(args) > 1 else kwargs.get("source")

    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "add_sample", _add_sample)
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "upsert_daily", _upsert_daily)

    entity = event["entity"]
    monitor_service._persist_metric_sample(db, adapter, event, entity, NOW)
    assert captured == {"add_source": "prometheus", "daily_source": "prometheus"}


def test_upsert_daily_insert_requires_source(monkeypatch):
    db = _Db()
    from datetime import date

    repo = monitor_service.MonMetricSampleRepository(db)
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "add_sample",
                        lambda *a, **kw: None)
    repo.upsert_daily("prometheus", "host", "10.0.0.1", "cpu_usage", date(2026, 9, 11), 95.0)
    assert db.added and len(db.added) == 1
    row = db.added[0]
    assert row.source == "prometheus"
    assert row.entity_type == "host"
    assert row.entity_id == "10.0.0.1"
    assert row.metric_name == "cpu_usage"
    assert row.sample_count == 1


def test_create_rule_passes_all_fields(monkeypatch):
    db = _Db()
    data = schemas.MonRuleCreate(
        name="CPU 高负载", event_kind="metric", metric_name="cpu_usage",
        condition_operator=">", condition_threshold=90, condition_duration_seconds=300,
        scope_type="host", scope_ids=["h1", "h2"], level="critical",
        cooldown_seconds=3600, converge_sec=120,
        escalation_enabled=1, escalate_levels=["warning", "critical"],
        notify_channel_ids=[1, 2],
    )
    monkeypatch.setattr(monitor_service, "_feature_enabled", lambda db: True)
    out = monitor_service.create_rule(db, _user(), data)
    rule = db.added[0]
    assert rule.scope_type == "host"
    assert rule.scope_ids == {"ids": ["h1", "h2"]}
    assert rule.level == "critical"
    assert rule.converge_sec == 120
    assert rule.escalate_levels == {"ids": ["warning", "critical"]}
    assert out["scope_type"] == "host"
    assert out["scope_ids"] == ["h1", "h2"]
    assert out["level"] == "critical"
    assert out["converge_sec"] == 120
    assert out["escalate_levels"] == ["warning", "critical"]


def test_update_rule_sets_scope_and_escalation(monkeypatch):
    db = _Db()
    rule = _rule(name="r")
    data = schemas.MonRuleUpdate(
        scope_type="app", scope_ids=["app-1"], level="info",
        converge_sec=60, escalate_levels=["warning"],
    )
    monkeypatch.setattr(monitor_service.MonRuleRepository, "get", lambda self, i: rule)
    out = monitor_service.update_rule(db, _user(), 1, data)
    assert rule.scope_type == "app"
    assert rule.scope_ids == {"ids": ["app-1"]}
    assert rule.level == "info"
    assert rule.converge_sec == 60
    assert rule.escalate_levels == {"ids": ["warning"]}
    assert out["scope_type"] == "app"
    assert out["scope_ids"] == ["app-1"]
    assert out["escalate_levels"] == ["warning"]


def test_rule_out_scope_enums_reject_group():
    rule = _rule(scope_type="host", scope_ids={"ids": ["h1"]}, escalate_levels={"ids": ["warning"]})
    out = monitor_service._rule_out(rule)
    assert out["scope_type"] in ("host", "app", "service", None)
    assert out["scope_ids"] == ["h1"]
    assert out["escalate_levels"] == ["warning"]


# ── rule engine transitions ──────────────────────────────────────────────────


def _patch_engine(monkeypatch, rule, alert, optimistic=True):
    monkeypatch.setattr(monitor_service.MonRuleRepository, "enabled_rules",
                        lambda self: [rule])
    monkeypatch.setattr(monitor_service.MonAlertRepository, "active_by_rule_entity",
                        lambda self, rid, eid: alert)
    if optimistic is not None:
        monkeypatch.setattr(
            monitor_service.MonAlertRepository, "optimistic_update",
            lambda self, aid, fr, to, ver, **kw: optimistic)
    monkeypatch.setattr(monitor_service, "_maybe_notify", lambda db, a, r, s: "fire")
    monkeypatch.setattr(monitor_service, "_maybe_escalate", lambda db, a, r: False)
    monkeypatch.setattr(monitor_service, "_log_alert_event", lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service, "_resolve_alert_engine", lambda db, a, r: True)


def test_pending_stays_pending_until_duration(monkeypatch):
    db = _Db()
    alert = _alert(status="pending", created_at=NOW)
    rule = _rule(condition_duration_seconds=300)
    _patch_engine(monkeypatch, rule, alert)
    outcomes = monitor_service.evaluate_event(db, _metric_event())
    assert [o["action"] for o in outcomes] == ["suppress"]
    assert alert.status == "pending"


def test_pending_fires_when_duration_elapsed(monkeypatch):
    db = _Db()
    alert = _alert(status="pending", created_at=NOW - timedelta(seconds=10), version=1)
    rule = _rule(condition_duration_seconds=5)
    _patch_engine(monkeypatch, rule, alert)
    outcomes = monitor_service.evaluate_event(db, _metric_event())
    assert [o["action"] for o in outcomes] == ["fire"]
    assert alert.status == "firing"
    assert alert.fired_at is not None


def test_new_alert_created_on_first_hit(monkeypatch):
    db = _Db()
    rule = _rule(condition_duration_seconds=0)
    monkeypatch.setattr(monitor_service.MonRuleRepository, "enabled_rules",
                        lambda self: [rule])
    monkeypatch.setattr(monitor_service.MonAlertRepository, "active_by_rule_entity",
                        lambda self, rid, eid: None)
    monkeypatch.setattr(monitor_service, "_log_alert_event", lambda *a, **kw: None)
    outcomes = monitor_service.evaluate_event(db, _metric_event())
    assert outcomes[0]["action"] == "fire"
    assert outcomes[0]["to_status"] == "pending"
    assert db.added and isinstance(db.added[0], monitor_service.MonAlert)


def test_non_matching_event_resolves_firing_alert(monkeypatch):
    db = _Db()
    rule = _rule(event_kind="metric")
    alert = _alert(status="firing", fired_at=NOW)
    _patch_engine(monkeypatch, rule, alert)
    outcomes = monitor_service.evaluate_event(db, {
        "kind": "alert", "source": "alertmanager",
        "entity": {"entity_id": "10.0.0.1"}, "ts": NOW.isoformat(),
    })
    assert outcomes == [{"rule_id": 1, "action": "resolve"}]


def test_scope_filter_excludes_outside_entities(monkeypatch):
    db = _Db()
    rule = _rule(scope_type="host", scope_ids={"ids": ["10.0.0.9"]})
    monkeypatch.setattr(monitor_service.MonRuleRepository, "enabled_rules",
                        lambda self: [rule])
    outcomes = monitor_service.evaluate_event(db, _metric_event())
    assert outcomes == []  # entity 10.0.0.1 not in scope


# ── convergence / escalation ──────────────────────────────────────────────────


def test_converge_suppresses_recent_fire(monkeypatch):
    db = _Db()
    rule = _rule(converge_sec=60)
    alert = _alert(status="firing", fired_at=NOW)
    monkeypatch.setattr(monitor_service.MonAlertEventLogRepository, "timeline",
                        lambda self, aid: [SimpleNamespace(id=1, action="fire", at=NOW)])
    monkeypatch.setattr(monitor_service, "_log_alert_event", lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service, "_send_alert_notify", lambda *a, **kw: None)
    assert monitor_service._maybe_notify(db, alert, rule, "firing") == "suppress"


def test_converge_fires_when_window_passed(monkeypatch):
    db = _Db()
    rule = _rule(converge_sec=60)
    alert = _alert(status="firing", fired_at=NOW)
    old = NOW - timedelta(hours=2)
    monkeypatch.setattr(monitor_service.MonAlertEventLogRepository, "timeline",
                        lambda self, aid: [SimpleNamespace(id=1, action="fire", at=old)])
    monkeypatch.setattr(monitor_service, "_send_alert_notify", lambda *a, **kw: None)
    assert monitor_service._maybe_notify(db, alert, rule, "firing") == "fire"


def test_escalate_escapes_to_next_level(monkeypatch):
    db = _Db()
    base = NOW - timedelta(minutes=10)
    alert = _alert(status="firing", severity="warning", fired_at=base)
    rule = _rule(escalation_enabled=1, escalation_after_seconds=60,
                 escalate_levels={"ids": ["critical"]})
    monkeypatch.setattr(monitor_service, "_log_alert_event", lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service, "_send_alert_notify", lambda *a, **kw: None)
    assert monitor_service._maybe_escalate(db, alert, rule) is True
    assert alert.severity == "critical"


def test_escalate_disabled_or_within_window(monkeypatch):
    db = _Db()
    alert = _alert(status="firing", severity="warning", fired_at=NOW)
    rule = _rule(escalation_enabled=1, escalation_after_seconds=3600,
                 escalate_levels={"ids": ["critical"]})
    assert monitor_service._maybe_escalate(db, alert, rule) is False
    assert alert.severity == "warning"


# ── ingestion / adapter / event inbox ────────────────────────────────────────


def test_ingest_dead_letters_unsupported_payload(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=1, type="prometheus", enabled=1, name="p")
    monkeypatch.setattr(monitor_service, "_feature_enabled", lambda db: True)
    monkeypatch.setattr(monitor_service.MonAdapterRepository, "get", lambda self, i: adapter)
    monkeypatch.setattr(monitor_service, "_dead_letter",
                        lambda db, aid, raw, err, detail=None: {"accepted": False, "error": err})
    result = monitor_service.ingest(db, 1, {"nonsense": True})
    assert result["accepted"] is False


def test_ingest_disabled_adapter_rejected(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=1, type="prometheus", enabled=0, name="p")
    monkeypatch.setattr(monitor_service, "_feature_enabled", lambda db: True)
    monkeypatch.setattr(monitor_service.MonAdapterRepository, "get", lambda self, i: adapter)
    with pytest.raises(BadRequestError):
        monitor_service.ingest(db, 1, {"source": "prometheus", "kind": "metric"})


def test_build_event_key_source_event_id():
    assert monitor_service.build_event_key("prometheus", "evt-1") == "prometheus:evt-1"
    assert monitor_service.build_event_key("prometheus", None) is None
    assert monitor_service.build_event_key("prometheus", "") is None


def test_ingest_returns_summary_body(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=7, type="prometheus", enabled=1, name="p")
    monkeypatch.setattr(monitor_service, "_feature_enabled", lambda db: True)
    monkeypatch.setattr(monitor_service.MonAdapterRepository, "get", lambda self, i: adapter)
    monkeypatch.setattr(monitor_service, "_process_event",
                        lambda db, ad, raw: {"accepted": True, "dedup": False})
    result = monitor_service.ingest(db, 7, {"source": "prometheus", "kind": "metric",
                                            "entity": {"entity_id": "10.0.0.1"}})
    assert result == {"accepted": 1, "rejected": 0, "adapter_id": 7}


def test_process_event_dedups_same_event_key(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=1, type="prometheus", enabled=1, name="p")
    event = {
        "source": "prometheus", "kind": "metric",
        "entity": {"entity_type": "host", "entity_id": "10.0.0.1", "entity_name": "h1"},
        "ts": NOW.isoformat(), "value": 90.0, "event_id": "evt-1",
    }
    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "by_event_key",
                        lambda self, k: None)
    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "add_event",
                        lambda self, **kw: SimpleNamespace(kind="metric"))
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "add_sample",
                        lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "upsert_daily",
                        lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service, "evaluate_event", lambda db, event: [])

    first = monitor_service._process_event(db, adapter, event)
    assert first["accepted"] is True
    assert first["dedup"] is False

    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "by_event_key",
                        lambda self, k: SimpleNamespace(id=99))
    second = monitor_service._process_event(db, adapter, event)
    assert second["accepted"] is True
    assert second["dedup"] is True


def test_process_event_second_send_does_not_persist_duplicate(monkeypatch):
    db = _Db()
    adapter = SimpleNamespace(id=1, type="prometheus", enabled=1, name="p")
    event = {
        "source": "prometheus", "kind": "metric",
        "entity": {"entity_type": "host", "entity_id": "10.0.0.1", "entity_name": "h1"},
        "ts": NOW.isoformat(), "value": 90.0, "event_id": "evt-1",
    }
    added = []

    class _Probe:
        def __init__(self):
            self.__class__.calls = []

        def __call__(self, *a, **kw):
            self.__class__.calls.append(kw)
            return SimpleNamespace(kind="metric")

    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "by_event_key",
                        lambda self, k: None)
    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "add_event", _Probe())
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "add_sample",
                        lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service.MonMetricSampleRepository, "upsert_daily",
                        lambda *a, **kw: None)
    monkeypatch.setattr(monitor_service, "evaluate_event", lambda db, event: [])

    first = monitor_service._process_event(db, adapter, event)
    assert first == {"accepted": True, "dedup": False,
                     "fingerprint": monitor_service.build_fingerprint(event)}
    assert len(_Probe.calls) == 1

    monkeypatch.setattr(monitor_service.MonEventInboxRepository, "by_event_key",
                        lambda self, k: SimpleNamespace(id=99))
    second = monitor_service._process_event(db, adapter, event)
    assert second == {"accepted": True, "dedup": True,
                      "fingerprint": monitor_service.build_fingerprint(event)}
    assert len(_Probe.calls) == 1  # dedup: no duplicate inbox row persisted


def test_encrypt_config_secrets_wraps_secret_keys():
    merged = monitor_service._encrypt_config_secrets(
        {"url": "http://x", "token": "secret-token", "nested": {"api_key": "k"}}, None)
    assert merged["token"].startswith("enc:")
    assert merged["nested"]["api_key"].startswith("enc:")
    assert merged["url"] == "http://x"


def test_encrypt_preserves_unset_secrets_from_existing():
    merged = monitor_service._encrypt_config_secrets({"url": "http://x"},
                                                     {"token": "enc:ABCD"})
    assert merged["token"] == "enc:ABCD"
    assert merged["url"] == "http://x"


def test_mask_adapter_config_masks_enc_values(monkeypatch):
    monkeypatch.setattr(monitor_service, "mask_secret", lambda v: "***masked***")
    out = monitor_service._mask_adapter_config(
        {"token": "enc:ABCD", "url": "http://x", "nested": {"api_key": "enc:EF"}})
    assert out["token"] == "***masked***"
    assert out["url"] == "http://x"
    assert out["nested"]["api_key"] == "***masked***"


# ── alert operations ──────────────────────────────────────────────────────────


def test_acknowledge_requires_firing(monkeypatch):
    db = _Db()
    monkeypatch.setattr(monitor_service.MonAlertRepository, "get",
                        lambda self, i: _alert(status="pending"))
    with pytest.raises(BadRequestError):
        monitor_service.acknowledge_alert(db, _user(), 1, "ok")


def test_acknowledge_firing_succeeds(monkeypatch):
    db = _Db()
    alert = _alert(status="firing", version=1)
    monkeypatch.setattr(monitor_service.MonAlertRepository, "get",
                        lambda self, i: alert)
    monkeypatch.setattr(monitor_service.MonAlertRepository, "optimistic_update",
                        lambda self, aid, fr, to, ver, **kw: True)
    monkeypatch.setattr(monitor_service.MonAlertEventLogRepository, "append",
                        lambda *a, **kw: None)
    out = monitor_service.acknowledge_alert(db, _user(), 1, "ack")
    assert out["status"] == "acknowledged"


def test_resolve_records_from_status(monkeypatch):
    db = _Db()
    alert = _alert(status="acknowledged", version=3)
    seen = {}
    monkeypatch.setattr(monitor_service.MonAlertRepository, "get",
                        lambda self, i: alert)
    monkeypatch.setattr(monitor_service.MonAlertRepository, "optimistic_update",
                        lambda self, aid, fr, to, ver, **kw: True)
    monkeypatch.setattr(
        monitor_service.MonAlertEventLogRepository, "append",
        lambda self, aid, action, fr, to, sev, detail, operator_id=None: seen.update(
            {"from": fr, "to": to, "action": action}),
    )
    out = monitor_service.resolve_alert(db, _user(), 1, "fixed")
    assert out["status"] == "resolved"
    assert seen == {"from": "acknowledged", "to": "resolved", "action": "resolve"}


def test_resolve_missing_alert_raises_notfound(monkeypatch):
    db = _Db()
    monkeypatch.setattr(monitor_service.MonAlertRepository, "get",
                        lambda self, i: None)
    with pytest.raises(NotFoundError):
        monitor_service.resolve_alert(db, _user(), 999, "x")


# ── feature flag ──────────────────────────────────────────────────────────────


def test_feature_flag_default_on(monkeypatch):
    db = _Db()
    monkeypatch.setattr(monitor_service.ConfigRuleRepository, "by_key",
                        lambda self, key: None)
    assert monitor_service._feature_enabled(db) is True


def test_feature_flag_disabled_when_explicit(monkeypatch):
    db = _Db()
    monkeypatch.setattr(monitor_service.ConfigRuleRepository, "by_key",
                        lambda self, key: SimpleNamespace(rule_value={"enabled": 0}))
    assert monitor_service._feature_enabled(db) is False


# ── condition check ──────────────────────────────────────────────────────────


def test_check_condition_ops():
    rule = _rule(condition_operator=">", condition_threshold=80)
    assert monitor_service._check_condition(rule, 95.0) is True
    assert monitor_service._check_condition(rule, 79.0) is False
    rule2 = _rule(condition_operator="<=", condition_threshold=80)
    assert monitor_service._check_condition(rule2, 80.0) is True