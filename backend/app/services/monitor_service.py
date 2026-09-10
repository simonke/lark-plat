"""Monitor service (P2-MA): event ingestion/normalization (P4), rule engine with
alert lifecycle state machine (P2 pending/firing/acknowledged/resolved), adapter
CRUD + health, metrics query, alert acknowledge/resolve, WS token issuance.

Frozen contract (2026-09-09):
  - route prefix /monitor/*, WS /ws/monitor
  - mon_alert.status: pending/firing/acknowledged/resolved (suppressed is a
    transient convergence marker, not a persisted state)
  - mon_alert_event_log: action fire|acknowledge|escalate|resolve|suppress,
    append-only, CAS on mon_alert.version
  - MonEvent schema: source/kind/entity{entity_type,entity_id,entity_name}/ts/
    value/severity/labels/raw/fingerprint; schema failures dead-letter
  - entity mapping fallbacks -> entity_id=unknown + mapping_warning;
    severity fallback -> warning; source+event_id idempotency
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.models import (
    MON_ADAPTER_STATUSES,
    MON_ADAPTER_TYPES,
    MON_ALERT_ACTIONS,
    MON_ALERT_STATUSES,
    MON_EVENT_STATUSES,
    MON_KINDS,
    MON_LEVELS,
    MON_RULE_OPS,
    MON_SOURCES,
    ConfigRule,
    Host,
    MonAdapter,
    MonAlert,
    MonEventInbox,
    MonRule,
)
from app.repositories import (
    ConfigRuleRepository,
    HostRepository,
    MonAdapterRepository,
    MonAlertEventLogRepository,
    MonAlertRepository,
    MonEventInboxRepository,
    MonMetricSampleRepository,
    MonRuleRepository,
    NotifyChannelRepository,
)
from app import schemas

logger = logging.getLogger(__name__)

# Entity mapping fallback / schema-validation source identifiers
_VALID_SOURCES = set(MON_SOURCES) | {"alertmanager"}
_VALID_KINDS = set(MON_KINDS)
_VALID_LEVELS = set(MON_LEVELS)
_VALID_OPS = set(MON_RULE_OPS)
_VALID_ADAPTER_TYPES = set(MON_ADAPTER_TYPES)
_VALID_ADAPTER_STATUSES = set(MON_ADAPTER_STATUSES)

# Adapter config keys whose values are encrypted (AES-GCM "enc:" prefix)
_SECRET_KEYS = {"token", "password", "api_key", "secret", "client_secret", "secret_key",
                "access_key", "app_secret", "access_token"}

# Alert notify scene (reuses one-phase notify module, add-only scene)
NOTIFY_SCENE = "alert"


def _get_json_list(value: Any) -> list:
    """Extract a list from either a dict with 'ids' key or a raw list."""
    if isinstance(value, dict):
        return list(value.get("ids") or [])
    return list(value or [])


def _feature_enabled(db: Session) -> bool:
    """feature.monitor config_rule namespace: disabled only when explicitly turned off."""
    rule = ConfigRuleRepository(db).by_key("feature.monitor")
    if rule and (rule.rule_value or {}).get("enabled") == 0:
        return False
    return True


# =============================================================== schema (P4)


def validate_event(event: dict) -> tuple[bool, str]:
    """Validate a normalized MonEvent against the frozen schema. Returns
    (valid, error). metric kind requires value; source/kind are enum-checked."""
    source = event.get("source")
    kind = event.get("kind")
    if source not in _VALID_SOURCES:
        return False, f"invalid source: {source}"
    if kind not in _VALID_KINDS:
        return False, f"invalid kind: {kind}"
    entity = event.get("entity")
    if not isinstance(entity, dict) or not entity.get("entity_id"):
        return False, "entity.entity_id required"
    if not event.get("ts"):
        return False, "ts required"
    if kind == "metric" and not isinstance(event.get("value"), (int, float)):
        return False, "metric kind requires numeric value"
    return True, ""


def build_fingerprint(event: dict) -> str:
    """sha256 of the canonical MonEvent core (source/kind/entity/ts/value/severity/labels)."""
    core = {
        "source": event.get("source"),
        "kind": event.get("kind"),
        "entity": event.get("entity"),
        "ts": event.get("ts") and str(event.get("ts")),
        "value": event.get("value"),
        "severity": event.get("severity"),
        "labels": event.get("labels") or {},
    }
    canonical = json.dumps(core, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_event_key(source: str, event_id: str | None) -> str | None:
    if not event_id:
        return None
    return f"{source}:{event_id}"


# ============================================================== normalization

_MAPPING_FALLBACK_ENTITY = {"entity_type": "host", "entity_id": "unknown", "entity_name": "unknown"}


def _severity_from_status(status: str | None) -> str:
    mapping = {
        "critical": "critical", "error": "warning", "warning": "warning",
        "warn": "warning", "info": "info", "firing": "warning", "pending": "info",
    }
    return mapping.get((status or "").lower(), "warning")  # unknown -> warning fallback


def normalize_alertmanager(payload: dict) -> tuple[list[dict], Any]:
    """Alertmanager webhook payload -> normalized MonEvents (kind=alert)."""
    events: list[dict] = []
    for alert in payload.get("alerts", []) or []:
        labels = dict(alert.get("labels") or {})
        entity_id = labels.get("instance") or labels.get("host") or "unknown"
        entity_name = labels.get("hostname") or labels.get("node") or entity_id
        status = payload.get("status") or alert.get("status") or "firing"
        events.append({
            "source": "alertmanager",
            "kind": "alert",
            "entity": {"entity_type": "host", "entity_id": entity_id, "entity_name": entity_name},
            "ts": alert.get("startsAt") or payload.get("now") or _now_iso(),
            "value": None,
            "severity": _severity_from_status(labels.get("severity") or status),
            "labels": labels,
            "raw": {"alert": alert, "status": status},
            "event_id": labels.get("alertname") or str(alert.get("fingerprint") or ""),
        })
    return events, {"mapping_warning": 0, "kind": "alert"}


def normalize_prometheus_remote(payload: dict) -> tuple[list[dict], Any]:
    """Prometheus remote_write -> normalized MonEvents (kind=metric)."""
    events: list[dict] = []
    for series in payload.get("metric", []) or []:
        labels = dict(series.get("labels") or {})
        values = series.get("samples") or series.get("values") or []
        entity_id = labels.get("instance") or "unknown"
        entity_name = labels.get("hostname") or entity_id
        scrape_error = "missing_instance_label" if entity_id == "unknown" else ""
        for s in values:
            ts = s.get("ts") if isinstance(s, dict) else (s[0] if isinstance(s, list) and len(s) > 1 else None)
            value = s.get("value") if isinstance(s, dict) else (s[1] if isinstance(s, list) and len(s) > 1 else None)
            label_name = labels.get("__name__") or labels.get("metric_name") or (series.get("name") or "unknown")
            events.append({
                "source": "prometheus",
                "kind": "metric",
                "entity": {"entity_type": "host", "entity_id": entity_id, "entity_name": entity_name},
                "ts": ts or _now_iso(),
                "value": _to_float(value),
                "severity": None,
                "labels": {**labels, "metric_name": label_name},
                "raw": {"job": labels.get("job"), "scrape_error": scrape_error} if scrape_error else {"job": labels.get("job")},
                "event_id": None,
            })
    return events, {"mapping_warning": 1 if not events else 0, "kind": "metric"}


def normalize_event(source: str, payload: Any) -> tuple[list[dict], dict]:
    """Dispatch raw external payloads to the per-source normalizer.

    Returns (events, meta) where meta marks mapping_warning/kind. Unknown source
    shapes yield an empty event list (caller may dead-letter)."""
    if source == "prometheus":
        return normalize_prometheus_remote(payload)
    if source in ("alertmanager", "webhook") or (isinstance(payload, dict) and "alerts" in payload):
        return normalize_alertmanager(payload)
    if source == "elk":
        events = []
        docs = payload.get("hits") or payload.get("docs") or []
        for doc in docs:
            src = doc.get("_source") if isinstance(doc, dict) else {}
            if not isinstance(src, dict):
                src = {}
            log_level = src.get("log.level") or src.get("level") or "info"
            events.append({
                "source": "elk",
                "kind": "log" if log_level.lower() not in ("error", "fatal") else "alert",
                "entity": {"entity_type": "host",
                           "entity_id": src.get("host.name") or "unknown",
                           "entity_name": src.get("host.name") or "unknown"},
                "ts": src.get("@timestamp") or _now_iso(),
                "value": None,
                "severity": _severity_from_status(log_level),
                "labels": {"log_level": log_level, "service": src.get("service", {}).get("name")
                           if isinstance(src.get("service"), dict) else src.get("service")},
                "raw": src,
                "event_id": src.get("event_id"),
            })
        return events, {"mapping_warning": 1 if not events else 0, "kind": "log"}
    if source == "skywalking":
        status = payload.get("status") or payload.get("statusCode") or "UNKNOWN"
        events = [{
            "source": "skywalking",
            "kind": "apm",
            "entity": {"entity_type": "app",
                       "entity_id": payload.get("entity") or payload.get("service") or "unknown",
                       "entity_name": payload.get("service") or payload.get("entity") or "unknown"},
            "ts": payload.get("ts") or _now_iso(),
            "value": _to_float(payload.get("value")),
            "severity": _severity_from_status(status),
            "labels": {"statusCode": status, **(payload.get("labels") or {})},
            "raw": payload,
            "event_id": payload.get("event_id"),
        }]
        return events, {"mapping_warning": 1 if status == "UNKNOWN" else 0, "kind": "apm"}
    return [], {"mapping_warning": 0, "kind": "metric"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


# =============================================================================
# Ingest pipeline (validated -> dedup -> inbox -> metric persistence -> rule eval)


def _mask_adapter_config(config: dict) -> dict:
    out: dict[str, Any] = {}
    for key, val in config.items():
        if isinstance(val, str) and val.startswith("enc:"):
            out[key] = mask_secret(val)
        elif isinstance(val, dict):
            out[key] = _mask_adapter_config(val)
        elif isinstance(val, list):
            out[key] = [_mask_adapter_config(v) if isinstance(v, dict) else v for v in val]
        else:
            out[key] = val
    return out


def _encrypt_config_secrets(config: dict, existing: dict | None = None) -> dict:
    """Encrypt secret keys with AES-GCM. Missing secrets are preserved from `existing`."""
    merged = dict(existing or {})
    for key, val in config.items():
        if key in _SECRET_KEYS and isinstance(val, str) and not val.startswith("enc:"):
            merged[key] = "enc:" + encrypt_secret(val)
        elif isinstance(val, dict):
            nested = merged.get(key) if isinstance(merged.get(key), dict) else {}
            merged[key] = _encrypt_config_secrets(val, nested)
        else:
            merged[key] = val
    return merged


def ingest(db: Session, adapter_id: int, payload: Any) -> dict:
    """POST /monitor/ingest/{adapter_id} entry - adapter lookup plus normalized handling."""
    if not _feature_enabled(db):
        raise BadRequestError("monitor feature disabled")
    adapter = MonAdapterRepository(db).get(adapter_id)
    if adapter is None:
        raise NotFoundError("adapter not found")
    if adapter.enabled != 1:
        raise BadRequestError("adapter disabled")

    if isinstance(payload, dict) and payload.get("source") and payload.get("adapter") is None:
        # A fully normalized MonEvent (or a list wrapper) was pushed directly.
        events: list[dict] = []
        if isinstance(payload.get("kind"), str):
            events = [payload]
        elif payload.get("events") is not None:
            events = payload["events"]
    else:
        # Raw external payload -> adapter-source normalization
        events, _meta = normalize_event(adapter.type, payload)

    if not events:
        return _dead_letter(db, adapter_id, None, "unsupported payload shape",
                            {"adapter_id": adapter_id})

    accepted = 0
    rejected = 0
    for raw in events:
        result = _process_event(db, adapter, raw)
        if result.get("accepted"):
            accepted += 1
        else:
            rejected += 1
            if result.get("error"):
                _dead_letter(db, adapter.id, raw, result["error"])
    db.commit()
    return {"accepted": accepted, "rejected": rejected, "adapter_id": adapter_id}


def _process_event(db: Session, adapter: MonAdapter, raw: dict) -> dict:
    """Validate -> dedup -> persist inbox -> metric persistence -> rule evaluate."""
    valid, error = validate_event(raw)
    if not valid:
        return {"accepted": False, "error": error}

    fingerprint = raw.get("fingerprint") or build_fingerprint(raw)
    event_key = build_event_key(raw.get("source", adapter.type), raw.get("event_id"))
    if event_key:
        existing = MonEventInboxRepository(db).by_event_key(event_key)
        if existing is not None:
            return {"accepted": True, "dedup": True, "fingerprint": fingerprint}

    entity = raw.get("entity") or dict(_MAPPING_FALLBACK_ENTITY)
    mapping_warning = 0
    if entity.get("entity_id") in (None, "", "unknown"):
        mapping_warning = 1

    severity = (raw.get("severity") or "warning").lower()
    if severity not in _VALID_LEVELS:
        severity = "warning"
        mapping_warning = 1

    ts = _coerce_ts(raw.get("ts"))

    inbox = MonEventInboxRepository(db).add_event(
        source=raw.get("source", adapter.type),
        kind=raw.get("kind", "metric"),
        entity=entity,
        ts=ts,
        value=_to_float(raw.get("value")),
        severity=severity,
        labels=raw.get("labels") or {},
        raw=raw.get("raw"),
        fingerprint=fingerprint,
        event_key=event_key,
        mapping_warning=mapping_warning,
        status="pending",
    )

    if inbox.kind == "metric":
        _persist_metric_sample(db, adapter, raw, entity, ts)

    evaluate_event(db, raw)
    return {"accepted": True, "dedup": False, "fingerprint": fingerprint}


def _coerce_ts(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _persist_metric_sample(db: Session, adapter: MonAdapter, raw: dict, entity: dict, ts: datetime) -> None:
    value = _to_float(raw.get("value"))
    if value is None:
        return
    metric_name = (raw.get("labels") or {}).get("metric_name") or (raw.get("labels") or {}).get("__name__") or "unknown"
    entity_type = entity.get("entity_type") or "host"
    entity_id = str(entity.get("entity_id") or "unknown")
    entity_name = entity.get("entity_name") or entity_id
    fingerprint = raw.get("fingerprint") or build_fingerprint(raw)
    MonMetricSampleRepository(db).add_sample(
        entity_type, entity_id, entity_name, metric_name, value,
        raw.get("source", adapter.type), ts, labels=raw.get("labels"), fingerprint=fingerprint,
    )
    MonMetricSampleRepository(db).upsert_daily(entity_type, entity_id, metric_name, ts.date(), value)



def _dead_letter(db: Session, adapter_id: int | None, raw: dict | None, error: str,
                 detail: dict | None = None) -> dict:
    try:
        MonEventInboxRepository(db).add_event(
            source=(raw or {}).get("source", "webhook"),
            kind=(raw or {}).get("kind", "metric"),
            entity=(raw or {}).get("entity") or dict(_MAPPING_FALLBACK_ENTITY),
            ts=_coerce_ts((raw or {}).get("ts")) if raw else datetime.now(timezone.utc),
            value=_to_float((raw or {}).get("value")) if raw else None,
            severity=(raw or {}).get("severity"),
            labels=(raw or {}).get("labels"),
            raw=raw,
            fingerprint=(raw or {}).get("fingerprint") or "dead-letter",
            status="dead_letter",
            error=(error[:512]) if detail is None else (error[:464] + json.dumps(detail, ensure_ascii=False)[:64]),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - dead-letter bookkeeping must not raise
        db.rollback()
    logger.warning("monitor: event dead-lettered (adapter=%s): %s", adapter_id, error)
    return {"accepted": False, "error": error}


# =============================================================================
# Rule engine (P2) - alert lifecycle state machine

_TRANSITIONS = {
    ("pending", "fire"): "firing",
    ("firing", "resolve"): "resolved",
    ("firing", "acknowledge"): "acknowledged",
    ("acknowledged", "resolve"): "resolved",
    ("resolved", "fire"): "pending",
}


def _rule_matches(rule: MonRule, event: dict) -> tuple[bool, str]:
    """Check whether a normalized event pertains to a rule (kind + source + metric + scope)."""
    kind = event.get("kind")
    if kind != rule.event_kind:
        return False, ""
    if rule.event_source and rule.event_source != event.get("source"):
        return False, ""

    if rule.event_kind == "metric":
        metric_name = (event.get("labels") or {}).get("metric_name") or \
                      (event.get("labels") or {}).get("__name__") or ""
        if rule.metric_name and metric_name != rule.metric_name:
            return False, ""

    # US-03: server-side entity scope filtering
    if rule.scope_type:
        entity = event.get("entity") or {}
        scope = _get_json_list(rule.scope_ids)
        if scope and str(entity.get("entity_id")) not in scope:
            return False, ""

    return True, ""


def evaluate_event(db: Session, event: dict) -> list[dict]:
    """Public rule-eval entry: run one normalized event through every enabled rule
    and return per-rule outcome records (fire/resolve/suppress + state)."""
    outcomes: list[dict] = []
    now = datetime.now(timezone.utc)
    for rule in MonRuleRepository(db).enabled_rules():
        matched, _reason = _rule_matches(rule, event)
        alert_repo = MonAlertRepository(db)
        alert = alert_repo.active_by_rule_entity(rule.id, (event.get("entity") or {}).get("entity_id"))
        if not matched:
            if alert is not None and alert.fired_at:
                _resolve_alert_engine(db, alert, "condition not met")
                outcomes.append({"rule_id": rule.id, "action": "resolve"})
            continue

        if alert is None:
            alert = MonAlert(
                rule_id=rule.id,
                rule_name=rule.name,
                entity=event.get("entity") or dict(_MAPPING_FALLBACK_ENTITY),
                source=event.get("source", "agent"),
                status="pending",
                severity=event.get("severity", "warning"),
                last_value=_to_float(event.get("value")),
                hit_count=1,
            )
            alert_repo.add(alert)
            db.flush()
            _log_alert_event(db, alert, "fire", None, "pending", alert.severity,
                             {"reason": "first condition hit"})
            outcomes.append({"rule_id": rule.id, "action": "fire", "to_status": "pending"})
            continue

        alert.hit_count += 1
        alert.last_value = _to_float(event.get("value"))
        now = datetime.now(timezone.utc)

        if alert.status in ("pending",):
            elapsed = (now - alert.created_at).total_seconds()
            if elapsed >= rule.condition_duration_seconds:
                if alert_repo.optimistic_update(alert.id, "pending", "firing", alert.version,
                                                fired_at=now, last_value=alert.last_value):
                    alert.version += 1
                    alert.status = "firing"
                    alert.fired_at = now
                    _log_alert_event(db, alert, "fire", "pending", "firing", alert.severity,
                                     {"condition_duration_seconds": rule.condition_duration_seconds})
                    outcome = _maybe_notify(db, alert, rule, "firing")
                    outcomes.append({"rule_id": rule.id, "action": outcome, "to_status": "firing"})
            else:
                _log_alert_event(db, alert, "suppress", "pending", "pending", alert.severity,
                                 {"waiting_duration": True})
                outcomes.append({"rule_id": rule.id, "action": "suppress"})
        elif alert.status in ("firing", "acknowledged"):
            if alert_repo.optimistic_update(alert.id, alert.status, alert.status, alert.version,
                                            last_value=alert.last_value):
                alert.version += 1
            outcome = _maybe_notify(db, alert, rule, alert.status)
            escalated = _maybe_escalate(db, alert, rule)
            action = "escalate" if escalated else outcome
            outcomes.append({"rule_id": rule.id, "action": action, "to_status": alert.status})
    return outcomes


def _maybe_escalate(db: Session, alert: MonAlert, rule: MonRule) -> bool:
    if not rule.escalation_enabled or (rule.escalation_after_seconds or 0) <= 0 or not alert.fired_at:
        return False
    escalate_levels = _get_json_list(rule.escalate_levels)
    if not escalate_levels or alert.severity in escalate_levels:
        return False
    now = datetime.now(timezone.utc)
    if (now - alert.fired_at).total_seconds() < rule.escalation_after_seconds:
        return False
    target = escalate_levels[0]
    alert.severity = target
    _log_alert_event(db, alert, "escalate", "firing", "firing", target,
                     {"after_seconds": rule.escalation_after_seconds})
    _send_alert_notify(db, alert, rule, f"升级告警提醒：{alert.rule_name}")
    return True


def _resolve_alert_engine(db: Session, alert: MonAlert, reason: str) -> bool:
    if alert.status == "resolved":
        return False
    from_status = alert.status
    to_status = "resolved"
    repo = MonAlertRepository(db)
    if not repo.optimistic_update(alert.id, from_status, "resolved", alert.version,
                                  resolved_at=datetime.now(timezone.utc)):
        return False
    alert.version += 1
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    _log_alert_event(db, alert, "resolve", from_status, "resolved", alert.severity,
                     {"reason": reason})
    rule = MonRuleRepository(db).get(alert.rule_id) if alert.rule_id else None
    if rule is not None:
        _send_alert_notify(db, alert, rule, f"告警恢复：{alert.rule_name}")
    return True


def _maybe_notify(db: Session, alert: MonAlert, rule: MonRule, _status: str) -> str:
    """Convergence/dedup gate for notifications. Returns fired/store action."""
    cooldown_sec = max(rule.cooldown_seconds or 0, 0)
    if cooldown_sec > 0:
        last_log = MonAlertEventLogRepository(db).timeline(alert.id)
        sends = [e for e in last_log if e.action == "fire" and e.at]
        if sends:
            last_at = max(e.at for e in sends)
            if (datetime.now(timezone.utc) - last_at).total_seconds() < cooldown_sec:
                _log_alert_event(db, alert, "suppress", alert.status, alert.status,
                                 alert.severity, {"cooldown_window": 1})
                return "suppress"
    _send_alert_notify(db, alert, rule, f"告警触发：{alert.rule_name}")
    return "fire"


def _send_alert_notify(db: Session, alert: MonAlert, rule: MonRule, title: str) -> None:
    """Reuse one-phase notify module (scene=alert). Explicitly injectable for tests."""
    channel_ids = _get_json_list(rule.notify_channel_ids)
    if not channel_ids:
        return
    from app.services import notify_service

    entity = alert.entity or {}
    content = (f"告警对象: {entity.get('entity_name') or entity.get('entity_id')}\n"
               f"级别: {alert.severity}\n状态: {alert.status}\n"
               f"最近值: {alert.last_value}\n源: {alert.source}")
    for cid in channel_ids:
        try:
            notify_service.send(db, cid, NOTIFY_SCENE, "", title, content)
        except Exception:  # noqa: BLE001 - notify failure must not break the rule engine
            logger.warning("monitor: notify channel %s failed for alert %s", cid, alert.id)


def _log_alert_event(db: Session, alert: MonAlert, action: str, from_status: str | None,
                     to_status: str | None, severity: str | None, detail: dict | None) -> None:
    if action not in MON_ALERT_ACTIONS:
        return
    MonAlertEventLogRepository(db).append(
        alert.id, action, from_status, to_status, severity, detail or {}, operator_id=None
    )
    db.flush()


# =============================================================================
# Alert operations (REST)


def _alert_out(a: MonAlert, ts: str | None = None) -> dict:
    return {
        "id": a.id,
        "rule_id": a.rule_id,
        "rule_name": a.rule_name,
        "entity": a.entity or {},
        "source": a.source,
        "status": a.status,
        "severity": a.severity,
        "last_value": a.last_value,
        "fired_at": a.fired_at.isoformat() if a.fired_at else None,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "action": "fire",
        "ts": ts or (a.created_at.isoformat() if a.created_at else None),
    }


def list_alerts(db: Session, user, filters: dict, page: int, size: int) -> dict:
    user.require_perm("monitor:alert:list")
    rows, total = MonAlertRepository(db).search(filters, page, size)
    return {
        "list": [_alert_out(a) for a in rows],
        "total": total, "page": page, "size": size,
    }


def get_alert(db: Session, user, alert_id: int) -> dict:
    user.require_perm("monitor:alert:view")
    alert = MonAlertRepository(db).get(alert_id)
    if alert is None:
        raise NotFoundError("alert not found")
    data = _alert_out(alert)
    data["events"] = [
        {"id": e.id, "action": e.action, "from_status": e.from_status, "to_status": e.to_status,
         "severity": e.severity, "detail": e.detail,
         "operator_id": e.operator_id, "at": e.at.isoformat() if e.at else None}
        for e in MonAlertEventLogRepository(db).timeline(alert_id)
    ]
    return data


def alert_events(db: Session, user, alert_id: int) -> dict:
    user.require_perm("monitor:alert:view")
    alert = MonAlertRepository(db).get(alert_id)
    if alert is None:
        raise NotFoundError("alert not found")
    return {"list": MonAlertEventLogRepository(db).timeline(alert_id)}


def acknowledge_alert(db: Session, user, alert_id: int, remark: str) -> dict:
    user.require_perm("monitor:alert:ack")
    repo = MonAlertRepository(db)
    alert = repo.get(alert_id)
    if alert is None:
        raise NotFoundError("alert not found")
    if alert.status != "firing":
        raise BadRequestError(f"alert not firing (status={alert.status})")
    if not repo.optimistic_update(alert.id, "firing", "acknowledged", alert.version):
        raise ForbiddenError("alert changed concurrently")
    alert.version += 1
    alert.status = "acknowledged"
    MonAlertEventLogRepository(db).append(
        alert.id, "acknowledge", "firing", "acknowledged", alert.severity,
        {"remark": remark}, operator_id=user.id
    )
    db.commit()
    return _alert_out(alert)


def resolve_alert(db: Session, user, alert_id: int, remark: str) -> dict:
    user.require_perm("monitor:alert:resolve")
    repo = MonAlertRepository(db)
    alert = repo.get(alert_id)
    if alert is None:
        raise NotFoundError("alert not found")
    if alert.status not in ("pending", "firing", "acknowledged"):
        raise BadRequestError(f"alert already resolved (status={alert.status})")
    from_status = alert.status
    if not repo.optimistic_update(alert.id, from_status, "resolved", alert.version,
                                  resolved_at=datetime.now(timezone.utc)):
        raise ForbiddenError("alert changed concurrently")
    alert.version += 1
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    MonAlertEventLogRepository(db).append(
        alert.id, "resolve", from_status, "resolved",
        alert.severity, {"remark": remark}, operator_id=user.id
    )
    db.commit()
    return _alert_out(alert)


# =============================================================================
# Rules CRUD


def list_rules(db: Session, user, filters: dict, page: int, size: int) -> dict:
    user.require_perm("monitor:rule:list")
    rows, total = MonRuleRepository(db).search(filters, page, size)
    return {"list": [_rule_out(r) for r in rows], "total": total, "page": page, "size": size}


def create_rule(db: Session, user, data: schemas.MonRuleCreate) -> dict:
    user.require_perm("monitor:rule:add")
    if not _feature_enabled(db):
        raise BadRequestError("monitor feature disabled")
    if data.condition_operator not in _VALID_OPS:
        raise BadRequestError(f"invalid operator: {data.condition_operator}")
    rule = MonRule(
        name=data.name, description=data.description, enabled=data.enabled,
        event_source=data.event_source, event_kind=data.event_kind,
        metric_name=data.metric_name,
        condition_operator=data.condition_operator,
        condition_threshold=data.condition_threshold,
        condition_duration_seconds=data.condition_duration_seconds,
        cooldown_seconds=data.cooldown_seconds,
        escalation_enabled=data.escalation_enabled,
        escalation_after_seconds=data.escalation_after_seconds,
        escalation_severity=data.escalation_severity,
        notify_scene=data.notify_scene,
        notify_channel_ids={"ids": data.notify_channel_ids},
        created_by=user.id,
    )
    MonRuleRepository(db).add(rule)
    db.commit()
    return _rule_out(rule)


def update_rule(db: Session, user, rule_id: int, data: schemas.MonRuleUpdate) -> dict:
    user.require_perm("monitor:rule:edit")
    repo = MonRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None or rule.deleted:
        raise NotFoundError("rule not found")
    for field in ("name", "description", "enabled", "event_source", "event_kind", "metric_name",
                  "condition_operator", "condition_threshold", "condition_duration_seconds",
                  "cooldown_seconds", "escalation_enabled", "escalation_after_seconds",
                  "escalation_severity", "notify_scene"):
        val = getattr(data, field)
        if val is not None:
            setattr(rule, field, val)
    if data.notify_channel_ids is not None:
        rule.notify_channel_ids = {"ids": data.notify_channel_ids}
    db.commit()
    return _rule_out(rule)


def delete_rule(db: Session, user, rule_id: int) -> dict:
    user.require_perm("monitor:rule:del")
    repo = MonRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None or rule.deleted:
        raise NotFoundError("rule not found")
    rule.deleted = 1  # soft delete: triggered alerts keep their rule snapshot
    db.commit()
    return {"id": rule.id, "deleted": True}


def set_rule_status(db: Session, user, rule_id: int, enabled: int) -> dict:
    user.require_perm("monitor:rule:status")
    repo = MonRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None or rule.deleted:
        raise NotFoundError("rule not found")
    rule.enabled = enabled
    db.commit()
    return {"id": rule.id, "enabled": rule.enabled}


def test_rule(db: Session, user, rule_id: int) -> dict:
    user.require_perm("monitor:rule:test")
    repo = MonRuleRepository(db)
    rule = repo.get(rule_id)
    if rule is None or rule.deleted:
        raise NotFoundError("rule not found")
    matched = 0
    latest = MonMetricSampleRepository(db).latest_by_entity(None, rule.metric_name or None)
    for s in latest:
        outcome = _check_condition(rule, s.value)
        if outcome:
            matched += 1
    return {"rule_id": rule.id, "matched_samples": matched, "recent_samples": len(latest),
            "would_fire": matched > 0}


def _check_condition(rule: MonRule, value: float) -> bool:
    try:
        if rule.condition_operator == "=":
            return value == rule.condition_threshold
        if rule.condition_operator == "!=":
            return value != rule.condition_threshold
        if rule.condition_operator == ">":
            return value > rule.condition_threshold
        if rule.condition_operator == "<":
            return value < rule.condition_threshold
        if rule.condition_operator == ">=":
            return value >= rule.condition_threshold
        if rule.condition_operator == "<=":
            return value <= rule.condition_threshold
    except TypeError:
        return False
    return False


def _rule_out(r: MonRule) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description,
        "event_kind": r.event_kind, "event_source": r.event_source,
        "metric_name": r.metric_name,
        "condition_operator": r.condition_operator,
        "condition_threshold": r.condition_threshold,
        "condition_duration_seconds": r.condition_duration_seconds,
        "cooldown_seconds": r.cooldown_seconds,
        "escalation_enabled": r.escalation_enabled,
        "escalation_after_seconds": r.escalation_after_seconds,
        "escalation_severity": r.escalation_severity,
        "notify_scene": r.notify_scene,
        "notify_channel_ids": _get_json_list(r.notify_channel_ids),
        "enabled": r.enabled,
        "created_by": r.created_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


# =============================================================================
# Adapters CRUD + health


def list_adapters(db: Session, user, enabled: int | None, type_: str | None,
                  page: int, size: int) -> dict:
    user.require_perm("monitor:rule:list")
    rows, total = MonAdapterRepository(db).search(enabled, type_, page, size)
    return {"list": [_adapter_out(a) for a in rows], "total": total, "page": page, "size": size}


def create_adapter(db: Session, user, data: schemas.MonAdapterCreate) -> dict:
    user.require_perm("monitor:rule:add")
    if not _feature_enabled(db):
        raise BadRequestError("monitor feature disabled")
    if data.type not in _VALID_ADAPTER_TYPES:
        raise BadRequestError(f"invalid adapter type: {data.type}")
    config = _encrypt_config_secrets(data.config or {}, None)
    adapter = MonAdapter(
        name=data.name, type=data.type, endpoint=data.endpoint,
        config=config, enabled=data.enabled, created_by=user.id,
    )
    MonAdapterRepository(db).add(adapter)
    db.commit()
    return _adapter_out(adapter)


def update_adapter(db: Session, user, adapter_id: int, data: schemas.MonAdapterUpdate) -> dict:
    user.require_perm("monitor:rule:edit")
    repo = MonAdapterRepository(db)
    adapter = repo.get(adapter_id)
    if adapter is None:
        raise NotFoundError("adapter not found")
    for field in ("name", "type", "endpoint", "enabled"):
        val = getattr(data, field)
        if val is not None:
            setattr(adapter, field, val)
    if data.config is not None:
        adapter.config = _encrypt_config_secrets(data.config, existing=adapter.config)
    db.commit()
    return _adapter_out(adapter)


def delete_adapter(db: Session, user, adapter_id: int) -> dict:
    user.require_perm("monitor:rule:del")
    repo = MonAdapterRepository(db)
    adapter = repo.get(adapter_id)
    if adapter is None:
        raise NotFoundError("adapter not found")
    db.delete(adapter)
    db.commit()
    return {"id": adapter_id, "deleted": True}


def set_adapter_status(db: Session, user, adapter_id: int, enabled: int) -> dict:
    user.require_perm("monitor:rule:status")
    repo = MonAdapterRepository(db)
    adapter = repo.get(adapter_id)
    if adapter is None:
        raise NotFoundError("adapter not found")
    adapter.enabled = enabled
    if not enabled:
        adapter.status = "disabled"
    db.commit()
    return {"id": adapter.id, "enabled": adapter.enabled, "status": adapter.status}


def test_adapter(db: Session, user, adapter_id: int) -> dict:
    user.require_perm("monitor:rule:test")
    repo = MonAdapterRepository(db)
    adapter = repo.get(adapter_id)
    if adapter is None:
        raise NotFoundError("adapter not found")
    config = _decrypted_adapter_config(adapter)
    endpoint = config.get("endpoint") or config.get("url") or config.get("server_uri")
    if adapter.type in ("prometheus", "elk", "webhook") and not endpoint:
        adapter.status = "degraded"
        adapter.error_msg = "endpoint not configured"
        db.commit()
        return {"ok": False, "latency_ms": None, "error_message": "endpoint not configured"}
    adapter.status = "healthy"
    adapter.error_msg = None
    adapter.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "latency_ms": None, "error_message": None}


def _decrypted_adapter_config(adapter: MonAdapter) -> dict:
    out: dict[str, Any] = {}
    for key, val in (adapter.config or {}).items():
        if isinstance(val, str) and val.startswith("enc:"):
            try:
                out[key] = decrypt_secret(val[4:])
            except Exception:  # noqa: BLE001
                out[key] = ""
        elif isinstance(val, dict):
            out[key] = _decrypted_adapter_config_val(val)
        else:
            out[key] = val
    return out


def _decrypted_adapter_config_val(val: dict) -> dict:
    out: dict[str, Any] = {}
    for key, v in val.items():
        if isinstance(v, str) and v.startswith("enc:"):
            try:
                out[key] = decrypt_secret(v[4:])
            except Exception:  # noqa: BLE001
                out[key] = ""
        elif isinstance(v, dict):
            out[key] = _decrypted_adapter_config_val(v)
        else:
            out[key] = v
    return out


def _adapter_out(a: MonAdapter) -> dict:
    return {
        "id": a.id, "name": a.name, "type": a.type, "endpoint": a.endpoint,
        "config_mask": _mask_adapter_config(a.config or {}),
        "enabled": a.enabled, "status": a.status,
        "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
        "metrics_received_count": a.metrics_received_count,
        "error_msg": a.error_msg,
        "created_by": a.created_by,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# =============================================================================
# Metrics + events + WS token


def query_metrics(db: Session, user, entity_ids: list[str] | None, group_id: int | None,
                  metric_name: str, start, end, agg: str, page: int, size: int) -> dict:
    user.require_perm("monitor:metric:view")
    if not user.is_admin and not entity_ids:
        entity_ids = HostRepository(db).entity_ids_in_groups(user.visible_group_ids)
    repo = MonMetricSampleRepository(db)
    if agg in ("5m", "1h", "1d"):
        rows = repo.query_bucketed(entity_ids, metric_name, start, end, agg)
        return {"agg": agg, "points": rows}
    rows, total = repo.query(entity_ids, metric_name, start, end, page, size)
    return {"agg": None, "points": [
        {"ts": r.ts.isoformat() if r.ts else None, "entity_id": r.entity_id,
         "value": r.value, "source": r.source} for r in rows
    ], "total": total, "page": page, "size": size}


def current_metrics(db: Session, user, entity_ids: list[str] | None, metric_name: str | None) -> dict:
    user.require_perm("monitor:metric:view")
    if not user.is_admin and not entity_ids:
        entity_ids = HostRepository(db).entity_ids_in_groups(user.visible_group_ids)
    rows = MonMetricSampleRepository(db).latest_by_entity(entity_ids, metric_name)
    return {"list": [
        {"entity_id": r.entity_id, "metric_name": r.metric_name, "value": r.value,
         "ts": r.ts.isoformat() if r.ts else None} for r in rows
    ]}


def list_events(db: Session, user, filters: dict, page: int, size: int) -> dict:
    user.require_perm("monitor:alert:view")
    rows, total = MonEventInboxRepository(db).search(filters, page, size)
    return {"list": [_event_out(e) for e in rows], "total": total, "page": page, "size": size}


def get_event(db: Session, user, event_id: int) -> dict:
    user.require_perm("monitor:alert:view")
    repo = MonEventInboxRepository(db)
    event = repo.get(event_id)
    if event is None:
        raise NotFoundError("event not found")
    return _event_out(event)


def _event_out(e: MonEventInbox) -> dict:
    return {
        "id": e.id, "source": e.source, "kind": e.kind, "entity": e.entity,
        "ts": e.ts.isoformat() if e.ts else None, "value": e.value, "severity": e.severity,
        "labels": e.labels, "raw": e.raw, "fingerprint": e.fingerprint,
        "mapping_warning": e.mapping_warning, "status": e.status, "error": e.error,
        "received_at": e.received_at.isoformat() if e.received_at else None,
    }


def ws_token(db: Session, user) -> dict:
    user.require_perm("monitor:alert:list")
    from app.ws.monitor_ws import create_ws_token

    return {"token": create_ws_token(user.id)}