"""Supervisor metrics: counters, gauges and event-mode families (OBS-003)."""

from __future__ import annotations

from typing import Any

from pumpgrok.supervisor.metrics import Metrics, build_registry

NINE = [
    "pumpgrok_cycle_seconds",
    "pumpgrok_bot_crashes_total",
    "pumpgrok_orders_total",
    "pumpgrok_equity_sol",
    "pumpgrok_drawdown_pct",
    "pumpgrok_data_age_seconds",
    "pumpgrok_breaker_state",
    "pumpgrok_kill_switch",
    "pumpgrok_ledger_seq",
]


def _family_names(metrics: Metrics) -> list[str]:
    out = metrics.exposition().decode()
    return [name for name in NINE if name in out]


def test_cadence_mode_exposes_exactly_the_nine_families() -> None:
    metrics = Metrics()
    exposition = metrics.exposition().decode()
    assert _family_names(metrics) == NINE
    assert "pumpgrok_events_total" not in exposition
    assert metrics.events is None
    assert metrics.registry is not None


def test_event_mode_adds_event_families() -> None:
    metrics = Metrics(event_mode=True)
    exposition = metrics.exposition().decode()
    assert _family_names(metrics) == NINE
    assert "pumpgrok_events_total" in exposition
    assert metrics.events is not None


def test_observe_records_duration_and_crashes() -> None:
    metrics = Metrics()
    metrics.observe("bot-01-scout", 2.5, "ok")
    metrics.observe("bot-01-scout", -1.0, "crash")
    exposition = metrics.exposition().decode()
    assert 'pumpgrok_cycle_seconds_count{seat="bot-01-scout"} 2.0' in exposition
    assert 'pumpgrok_cycle_seconds_sum{seat="bot-01-scout"} 2.5' in exposition
    assert 'pumpgrok_bot_crashes_total{seat="bot-01-scout"} 1.0' in exposition


def test_orders_note_and_sync_never_double_count() -> None:
    metrics = Metrics()
    metrics.note_order("buy", "filled")
    metrics.sync_orders({("buy", "filled"): 5.0})
    metrics.sync_orders({("buy", "filled"): 5.0})
    metrics.sync_orders({("buy", "filled"): 7.0})
    exposition = metrics.exposition().decode()
    assert 'pumpgrok_orders_total{outcome="filled",side="buy"} 7.0' in exposition
    metrics.sync_orders({("sell", "rejected"): 0.0})


def test_refresh_maps_snapshot_gauges() -> None:
    state: dict[str, Any] = {
        "equity_lamports": 2_000_000_000,
        "drawdown_pct": 3.5,
        "kill_switch": True,
        "ledger_seq": 42,
        "data_age": {"pumpportal": 12.0},
        "breakers": {"main": "open", "other": "weird-state"},
        "orders": {("buy", "filled"): 3.0},
    }
    metrics = Metrics(snapshot=lambda: dict(state))
    metrics.refresh()
    exposition = metrics.exposition().decode()
    assert "pumpgrok_equity_sol 2.0" in exposition
    assert "pumpgrok_drawdown_pct 3.5" in exposition
    assert "pumpgrok_kill_switch 1.0" in exposition
    assert "pumpgrok_ledger_seq 42.0" in exposition
    assert 'pumpgrok_data_age_seconds{source="pumpportal"} 12.0' in exposition
    assert 'pumpgrok_breaker_state{breaker="main"} 2.0' in exposition
    assert 'pumpgrok_breaker_state{breaker="other"} 2.0' in exposition
    # Stale series are removed when the snapshot drops them.
    state["data_age"] = {}
    state["breakers"] = {}
    metrics.refresh()
    exposition = metrics.exposition().decode()
    assert "pumpgrok_data_age_seconds{source=" not in exposition
    assert "pumpgrok_breaker_state{" not in exposition


def test_refresh_without_a_snapshot_is_a_noop() -> None:
    metrics = Metrics()
    metrics.refresh()
    assert metrics.exposition()  # never raises


def test_build_registry_returns_fresh_registries() -> None:
    first, second = build_registry(), build_registry()
    assert first is not second
