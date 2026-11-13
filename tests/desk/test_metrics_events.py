"""Event-mode metric families on the one registry and the one GET /metrics endpoint (EVT-12, GRK-10).

Cadence mode registers the nine OBS-003 families and nothing else, so its exposition bytes are
pinned. Event mode adds the event families after the nine on the same registry. The nine blocks
keep their bytes in both modes. Bus and gateway observations reach the scrape through a real
HealthServer, both from injected collectors and from a serve built by ``build_serve_replay``.
"""

from __future__ import annotations

import asyncio
import hashlib
import urllib.request
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.config.settings import FilterSettings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.errors import PoisonEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health import HealthServer
from pumpgrok.supervisor.metrics import NINE_FAMILIES, Metrics
from pumpgrok.supervisor.metrics_events import EVENT_FAMILIES
from pumpgrok.supervisor.scheduler import build_serve_replay

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"
SEED = 20260101
START = 1_800_000_000.0
#: sha256 of the cadence exposition for the scenario below, _created sample lines dropped.
#: Captured from the pre-change registry at HEAD; the nine blocks must never move.
CADENCE_SHA256 = "f9081ebd63e129ac15a91b256c17f46c811d8381a449ec4b2423bdc22152009d"


def _state() -> dict[str, Any]:
    return {
        "equity_lamports": 2_500_000_000,
        "drawdown_pct": 1.25,
        "data_age": {"ws": 0.5, "rest": 2.0},
        "breakers": {"buy": "closed", "sell": "half-open", "exit": "open"},
        "kill_switch": False,
        "ledger_seq": 42,
    }


def _cadence_scenario(metrics: Metrics) -> None:
    metrics.observe("bot-00-chief", 1.5, "ok")
    metrics.observe("bot-01-scout", 0.5, "crash")
    metrics.note_order("buy", "filled")
    metrics.note_order("sell", "rejected")
    metrics.note_order("buy", "unknown_result")


def _kept(body: str) -> str:
    """Drop only the ``*_created`` sample lines, whose values are wall-clock timestamps."""
    kept = [
        line
        for line in body.splitlines()
        if not line.split("{")[0].split(" ")[0].endswith("_created")
    ]
    return "\n".join(kept) + "\n"


async def _scrape(get_metrics: Callable[[], bytes]) -> str:
    """GET /metrics from a real HealthServer bound to loopback."""
    server = HealthServer(
        FixtureClock(start=0.0),
        lambda: {"status": "ok"},
        lambda: True,
        get_metrics=get_metrics,
    )
    port = await server.start("127.0.0.1", 0)
    try:

        def _get() -> bytes:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as resp:
                return resp.read()

        return (await asyncio.to_thread(_get)).decode("utf-8")
    finally:
        await server.stop()


async def _settle_until(done: Callable[[], bool]) -> None:
    for _ in range(200):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("bus did not settle")


def _request(text: str, *, now: float) -> GrokRequest:
    return GrokRequest(
        event_id=f"ev-{text}",
        agent="narrative",
        model="grok-test",
        prompt_sha="d" * 64,
        schema="verdict.v1",
        input={"mint": "EventMetricsMint1111111111111111111111111111"},
        text=text,
        candidate=Candidate(
            mint="EventMetricsMint1111111111111111111111111111",
            created_at=now - 600,
            first_trade_at=now - 300,
            unique_buyers=9,
            prerank=Decimal("0.8"),
            last_decision_at=None,
        ),
    )


def test_cadence_exposition_bytes_are_pinned() -> None:
    metrics = Metrics(snapshot=_state)
    _cadence_scenario(metrics)
    body = _kept(metrics.exposition().decode("utf-8"))
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == CADENCE_SHA256


def test_cadence_mode_registers_no_event_family() -> None:
    metrics = Metrics(snapshot=_state)
    assert metrics.events is None
    body = metrics.exposition().decode("utf-8")
    assert len(NINE_FAMILIES) == 9
    for family in EVENT_FAMILIES:
        assert family not in body, family


def test_event_mode_keeps_the_nine_blocks_byte_identical_and_appends_the_event_families() -> None:
    cadence = Metrics(snapshot=_state)
    _cadence_scenario(cadence)
    event = Metrics(snapshot=_state, event_mode=True)
    _cadence_scenario(event)
    cadence_body = _kept(cadence.exposition().decode("utf-8"))
    event_body = _kept(event.exposition().decode("utf-8"))
    assert event_body.startswith(cadence_body)
    tail = event_body[len(cadence_body) :]
    for family in EVENT_FAMILIES:
        assert f"# TYPE {family} counter" in tail, family


async def test_real_bus_observations_reach_the_scrape() -> None:
    metrics = Metrics(event_mode=True)
    events = metrics.events
    assert events is not None
    delivered: list[str] = []
    dlq: list[Event] = []

    async def handler(event: Event) -> None:
        if event.kind is EventKind.halt:
            raise PoisonEvent(index=0)
        delivered.append(event.entity_id)

    bus = EventBus(
        clock=FixtureClock(start=0.0),
        handler=events.observe_handler(handler),
        dlq=events.observe_dlq(dlq.append),
    )
    await bus.start()
    await bus.publish(
        Event(kind=EventKind.trade, entity_id="mintA", payload={"n": 1}, occurred_at="t1")
    )
    await bus.publish(
        Event(kind=EventKind.trade, entity_id="mintB", payload={"n": 2}, occurred_at="t2")
    )
    await bus.publish(
        Event(kind=EventKind.halt, entity_id="desk", payload={"reason": "x"}, occurred_at="t3")
    )
    await _settle_until(lambda: len(delivered) == 2 and len(dlq) == 1)
    await bus.shutdown()
    body = await _scrape(metrics.exposition)
    assert 'pumpgrok_events_total{kind="trade",outcome="delivered"} 2.0' in body
    assert 'pumpgrok_events_total{kind="halt",outcome="failed"} 1.0' in body
    assert 'pumpgrok_event_dlq_total{kind="halt"} 1.0' in body
    assert 'pumpgrok_event_dlq_total{kind="trade"}' not in body


async def test_real_gateway_transport_observations_reach_the_scrape(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    metrics = Metrics(event_mode=True)
    events = metrics.events
    assert events is not None
    calls: list[str] = []

    async def transport(_request: GrokRequest, text: str) -> str:
        calls.append(text)
        if "fail" in text:
            raise RuntimeError("upstream down")
        return "ok verdict"

    gateway = GrokGateway(
        clock=clock,
        transport=events.observe_transport(transport),
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )
    fresh = await gateway.admit(_request("market ok", now=clock.now()))
    cached = await gateway.admit(_request("market ok", now=clock.now()))
    failed = await gateway.admit(_request("market fail", now=clock.now()))
    assert (fresh.status, cached.status, failed.status) == ("fresh", "cache_hit", "rule_fallback")
    assert len(calls) == 2
    body = await _scrape(metrics.exposition)
    assert 'pumpgrok_grok_calls_total{agent="narrative",outcome="ok"} 1.0' in body
    assert 'pumpgrok_grok_calls_total{agent="narrative",outcome="error"} 1.0' in body


async def test_event_mode_serve_scrape_carries_bus_and_gateway_observations(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
        wake_mode="event",
    )
    try:
        events = metrics.events
        assert events is not None
        delivered: list[str] = []

        async def handler(event: Event) -> None:
            delivered.append(event.entity_id)

        bus = EventBus(
            clock=supervisor.clock,
            handler=events.observe_handler(handler),
            dlq=events.observe_dlq(lambda _event: None),
        )
        await bus.start()
        await bus.publish(
            Event(kind=EventKind.trade, entity_id="mintS", payload={"n": 1}, occurred_at="t1")
        )
        await _settle_until(lambda: len(delivered) == 1)
        await bus.shutdown()

        async def transport(_request: GrokRequest, _text: str) -> str:
            return "ok verdict"

        gateway = GrokGateway(
            clock=supervisor.clock,
            transport=events.observe_transport(transport),
            cache=ResponseCache(tmp_path / "cache.sqlite", supervisor.clock),
            budget=LayeredBudget(tmp_path / "budget.sqlite", supervisor.clock),
        )
        outcome = await gateway.admit(_request("serve market", now=supervisor.clock.now()))
        assert outcome.status == "fresh"
        body = await _scrape(metrics.exposition)
    finally:
        store.close()
    for family in NINE_FAMILIES:
        assert family in body, family
    assert 'pumpgrok_events_total{kind="trade",outcome="delivered"} 1.0' in body
    assert 'pumpgrok_grok_calls_total{agent="narrative",outcome="ok"} 1.0' in body


async def test_cadence_serve_scrape_has_no_event_family(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_700_000_000.0)
    supervisor, metrics, store = build_serve_replay(
        SMOKE,
        FilterSettings(),
        seed=SEED,
        clock=clock,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    try:
        assert supervisor.health_status()["ledger_source"] == "replay"
        assert metrics.events is None
        body = await _scrape(metrics.exposition)
    finally:
        store.close()
    for family in NINE_FAMILIES:
        assert family in body, family
    for family in EVENT_FAMILIES:
        assert family not in body, family
