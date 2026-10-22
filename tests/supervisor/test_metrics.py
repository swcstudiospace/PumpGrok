"""Metrics registry unit tests: nine families, seat hooks, exposition (OBS-003)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.supervisor.metrics import NINE_FAMILIES, Metrics, build_registry


def _snapshot() -> dict[str, Any]:
    return {
        "equity_lamports": 2_500_000_000,
        "drawdown_pct": 1.25,
        "data_age": {"ws": 0.5, "rest": 2.0},
        "breakers": {"buy": "closed", "sell": "half-open", "exit": "open"},
        "kill_switch": False,
        "ledger_seq": 42,
    }


def test_build_registry_returns_fresh_registry() -> None:
    assert build_registry() is not build_registry()


def test_exposition_carries_exactly_the_nine_names() -> None:
    metrics = Metrics(snapshot=_snapshot)
    metrics.observe("bot-00-chief", 1.5, "ok")
    metrics.observe("bot-01-scout", 0.5, "crash")
    metrics.note_order("buy", "filled")
    metrics.note_order("sell", "rejected")
    metrics.note_order("buy", "unknown_result")
    body = metrics.exposition().decode("utf-8")
    for family in NINE_FAMILIES:
        assert family in body, family
    assert len(NINE_FAMILIES) == 9
    pumpgrok_lines = {
        line.split("{")[0].split(" ")[0]
        for line in body.splitlines()
        if line
        and not line.startswith("#")
        and "pumpgrok_" in line
        and "_created" not in line.split("{")[0]
    }
    expected = {
        "pumpgrok_cycle_seconds_bucket",
        "pumpgrok_cycle_seconds_sum",
        "pumpgrok_cycle_seconds_count",
        "pumpgrok_bot_crashes_total",
        "pumpgrok_orders_total",
        "pumpgrok_equity_sol",
        "pumpgrok_drawdown_pct",
        "pumpgrok_data_age_seconds",
        "pumpgrok_breaker_state",
        "pumpgrok_kill_switch",
        "pumpgrok_ledger_seq",
    }
    assert pumpgrok_lines == expected, sorted(pumpgrok_lines ^ expected)


def test_cycle_seconds_histogram_uses_virtual_seconds() -> None:
    metrics = Metrics()
    metrics.observe("bot-00-chief", 2.5, "ok")
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_cycle_seconds_sum{seat="bot-00-chief"} 2.5' in body
    assert 'pumpgrok_cycle_seconds_count{seat="bot-00-chief"} 1.0' in body


def test_crash_outcome_counts_but_ok_does_not() -> None:
    metrics = Metrics()
    metrics.observe("bot-00-chief", 1.0, "ok")
    metrics.observe("bot-01-scout", 0.5, "crash")
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_bot_crashes_total{seat="bot-01-scout"} 1.0' in body
    assert "bot-00-chief" not in [
        line for line in body.splitlines() if line.startswith("pumpgrok_bot_crashes_total{")
    ]


def test_orders_counter_uses_declared_total_suffix() -> None:
    metrics = Metrics()
    metrics.note_order("buy", "filled")
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_orders_total{outcome="filled",side="buy"} 1.0' in body


def test_gauges_computed_at_scrape_time() -> None:
    state: dict[str, Any] = dict(_snapshot())
    metrics = Metrics(snapshot=lambda: state)
    first = metrics.exposition().decode("utf-8")
    assert "pumpgrok_equity_sol 2.5" in first
    assert "pumpgrok_drawdown_pct 1.25" in first
    assert "pumpgrok_kill_switch 0.0" in first
    assert "pumpgrok_ledger_seq 42.0" in first
    assert 'pumpgrok_data_age_seconds{source="ws"} 0.5' in first
    assert 'pumpgrok_breaker_state{breaker="buy"} 0.0' in first
    assert 'pumpgrok_breaker_state{breaker="sell"} 1.0' in first
    assert 'pumpgrok_breaker_state{breaker="exit"} 2.0' in first
    state["equity_lamports"] = 3_000_000_000
    state["kill_switch"] = True
    second = metrics.exposition().decode("utf-8")
    assert "pumpgrok_equity_sol 3.0" in second
    assert "pumpgrok_kill_switch 1.0" in second


def test_sync_orders_reconciles_from_ledger_without_double_count() -> None:
    metrics = Metrics()
    metrics.note_order("buy", "filled")
    metrics.sync_orders({("buy", "filled"): 5.0, ("sell", "rejected"): 2.0})
    metrics.sync_orders({("buy", "filled"): 5.0, ("sell", "rejected"): 2.0})
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_orders_total{outcome="filled",side="buy"} 5.0' in body
    assert 'pumpgrok_orders_total{outcome="rejected",side="sell"} 2.0' in body


def test_unknown_breaker_state_maps_to_open() -> None:
    metrics = Metrics(snapshot=lambda: {"breakers": {"buy": "mystery"}})
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_breaker_state{breaker="buy"} 2.0' in body


async def test_seat_run_guarded_drives_metrics_observer(tmp_path: Path) -> None:
    from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
    from pumpgrok.replay.clock import FixtureClock
    from pumpgrok.replay.rng import make_rng
    from pumpgrok.supervisor.seat_task import SeatContext, SeatTask

    recreate_ledger_db(tmp_path / "ledger.sqlite")
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    clock = FixtureClock(start=10.0)
    metrics = Metrics()

    async def _cycle(ctx: SeatContext) -> dict[str, Any]:
        # Move virtual time synchronously (see tests/logging/test_spans.py).
        clock.advance_to(clock.now() + 1.0)
        return {"ok": True}

    task = SeatTask(
        "bot-00-chief",
        60.0,
        _cycle,
        clock=clock,
        rng=make_rng(3),
        store=store,
        cycle_observer=metrics.observe,
    )
    ctx = SeatContext(
        seat_id="bot-00-chief",
        clock=clock,
        rng=make_rng(3),
        store=store,
        source="replay",
        correlation_id="desk",
    )
    assert await task.run_guarded(ctx) == "ok"
    body = metrics.exposition().decode("utf-8")
    assert 'pumpgrok_cycle_seconds_count{seat="bot-00-chief"} 1.0' in body
    assert 'pumpgrok_cycle_seconds_sum{seat="bot-00-chief"} 1.0' in body
    store.close()


async def test_metrics_route_serves_exposition_with_content_type() -> None:
    import asyncio
    import urllib.error
    import urllib.request

    from pumpgrok.replay.clock import FixtureClock
    from pumpgrok.supervisor.health import HealthServer
    from pumpgrok.supervisor.metrics import EXPOSITION_CONTENT_TYPE

    clock = FixtureClock(start=0.0)
    metrics = Metrics(snapshot=_snapshot)
    server = HealthServer(
        clock,
        lambda: {"status": "ok"},
        lambda: True,
        get_metrics=metrics.exposition,
    )
    port = await server.start("127.0.0.1", 0)
    try:

        def _fetch(path: str, method: str = "GET") -> tuple[int, str | None, bytes]:
            request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
            try:
                with urllib.request.urlopen(request) as response:
                    return (
                        int(response.status),
                        response.headers.get("Content-Type"),
                        response.read(),
                    )
            except urllib.error.HTTPError as exc:
                return (
                    int(exc.code),
                    exc.headers.get("Content-Type"),
                    exc.read(),
                )

        code, content_type, body = await asyncio.to_thread(_fetch, "/metrics")
        assert code == 200
        assert content_type == EXPOSITION_CONTENT_TYPE
        text = body.decode("utf-8")
        for family in NINE_FAMILIES:
            assert family in text, family
        code, content_type, _ = await asyncio.to_thread(_fetch, "/healthz")
        assert code == 200
        assert content_type == "application/json"
        code, _, _ = await asyncio.to_thread(_fetch, "/readyz")
        assert code == 200
        code, _, _ = await asyncio.to_thread(_fetch, "/metrics", "POST")
        assert code == 405
    finally:
        await server.stop()


async def test_metrics_route_without_provider_is_unavailable() -> None:
    import asyncio
    import urllib.error
    import urllib.request

    from pumpgrok.replay.clock import FixtureClock
    from pumpgrok.supervisor.health import HealthServer

    server = HealthServer(FixtureClock(start=0.0), lambda: {"status": "ok"}, lambda: True)
    port = await server.start("127.0.0.1", 0)
    try:

        def _fetch() -> int:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics")
                raise AssertionError("expected HTTPError")
            except urllib.error.HTTPError as exc:
                return int(exc.code)

        assert await asyncio.to_thread(_fetch) == 503
    finally:
        await server.stop()
