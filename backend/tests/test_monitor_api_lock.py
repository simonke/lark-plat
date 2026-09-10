"""P2-MA monitor API contract lock (route prefix, add-only over 71-path baseline).

Pins contract (2026-09-09):
  - route prefix /monitor/* (NOT /monitoring/*), WS /ws/monitor
  - 19 monitor paths added over the 71-path frozen baseline
"""

from __future__ import annotations

from app.api.v1.endpoints import monitor


def test_monitor_router_prefix_is_monitor_forward_slash():
    assert monitor.router.prefix == "/monitor"


def test_monitor_router_has_expected_paths():
    routes = {f"{sorted(r.methods)[0]}{r.path}" for r in monitor.router.routes if hasattr(r, "methods")}
    expected = {
        "GET/monitor/metrics",
        "GET/monitor/metrics/current",
        "GET/monitor/alerts",
        "GET/monitor/alerts/{alert_id}",
        "GET/monitor/alerts/{alert_id}/events",
        "POST/monitor/alerts/{alert_id}/acknowledge",
        "POST/monitor/alerts/{alert_id}/resolve",
        "GET/monitor/rules",
        "POST/monitor/rules",
        "PUT/monitor/rules/{rule_id}",
        "DELETE/monitor/rules/{rule_id}",
        "POST/monitor/rules/{rule_id}/status",
        "POST/monitor/rules/{rule_id}/test",
        "GET/monitor/adapters",
        "POST/monitor/adapters",
        "PUT/monitor/adapters/{adapter_id}",
        "DELETE/monitor/adapters/{adapter_id}",
        "POST/monitor/adapters/{adapter_id}/status",
        "POST/monitor/adapters/{adapter_id}/test",
        "GET/monitor/events",
        "GET/monitor/events/{event_id}",
        "POST/monitor/ingest/{adapter_id}",
        "GET/monitor/ws-token",
    }
    missing = expected - routes
    assert not missing, f"monitor router paths missing: {sorted(missing)}"


def test_monitor_ws_path_is_ws_monitor():
    from app.ws import monitor_ws

    ws_routes = [r.path for r in monitor_ws.router.routes if hasattr(r, "path")]
    assert "/ws/monitor" in ws_routes