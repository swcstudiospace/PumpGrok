# Offline tracer: validated observations are recorded before publication.

from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.datafeed.price import LivePriceSource
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.sources import SourceSupervisor
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.live_recorder import LiveRecorder


async def _handle(_event: Event) -> None:
    pass


class InspectingBus(EventBus):
    """Capture the actual recorder bytes at the real bus's publish boundary."""

    def __init__(self, *, clock: FixtureClock, events_path: Path) -> None:
        super().__init__(clock=clock, handler=_handle, dlq=lambda _event: None)
        self.events_path = events_path
        self.bytes_at_publish: list[bytes | None] = []

    async def publish(self, event: Event) -> None:
        self.bytes_at_publish.append(
            self.events_path.read_bytes() if self.events_path.is_file() else None
        )
        await super().publish(event)


def _observation(clock: FixtureClock) -> CurveObservation:
    return CurveObservation(
        mint="MintAAAA1111111111111111111111111111111111",
        ts_utc=clock.utc_iso(),
        s_lamports=42_000_000_000,
        t_units=764_608_076_000_000,
        complete=False,
        source="fixture-rpc",
    )


async def test_observation_is_recorded_before_real_bus_publication(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = _observation(clock)
    bus = InspectingBus(clock=clock, events_path=tmp_path / "events.jsonl")
    recorder = LiveRecorder(tmp_path, clock=clock)
    bridge = ObservationBridge(bus=bus, recorder=recorder)

    await bridge.publish(observation)

    published = bus.pending_p2(EventKind.curve_tick, observation.mint)
    assert published is not None
    assert published.kind is EventKind.curve_tick
    assert published.entity_id == observation.mint
    assert published.occurred_at == observation.ts_utc
    assert len(bus.bytes_at_publish) == 1
    recorded = bus.bytes_at_publish[0]
    assert recorded is not None
    tick = json.loads(recorded)
    assert tick == {
        "kind": "tick",
        "mint": observation.mint,
        "ts_utc": observation.ts_utc,
        "S": observation.s_lamports,
        "T": observation.t_units,
        "complete": False,
        "source": observation.source,
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("ts_utc", "not-a-timestamp"),
        ("ts_utc", "2026-01-01T00:00:00"),
        ("ts_utc", "2026-01-01T01:00:00+01:00"),
        ("complete", 1),
        ("source", ""),
        ("s_lamports", 0),
        ("s_lamports", -1),
        ("s_lamports", True),
        ("t_units", 0),
        ("t_units", -1),
        ("t_units", 1.5),
    ],
)
async def test_invalid_observation_is_refused_before_publication(
    tmp_path: Path, field: str, bad_value: object
) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = replace(_observation(clock), **{field: bad_value})
    bus = InspectingBus(clock=clock, events_path=tmp_path / "events.jsonl")
    bridge = ObservationBridge(bus=bus, recorder=LiveRecorder(tmp_path, clock=clock))

    with pytest.raises(ValueError):
        await bridge.publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is None
    assert bus.bytes_at_publish == []


async def test_recording_failure_prevents_publication(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = _observation(clock)
    bus = InspectingBus(clock=clock, events_path=tmp_path / "events.jsonl")

    class FailingRecorder(LiveRecorder):
        def record(self, observation: CurveObservation) -> None:
            raise OSError("disk failure")

    bridge = ObservationBridge(bus=bus, recorder=FailingRecorder(tmp_path, clock=clock))
    with pytest.raises(OSError, match="disk failure"):
        await bridge.publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is None
    assert bus.bytes_at_publish == []


async def test_coalescing_does_not_drop_recorded_ticks(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    first = _observation(clock)
    bus = InspectingBus(clock=clock, events_path=tmp_path / "events.jsonl")
    recorder = LiveRecorder(tmp_path, clock=clock)
    bridge = ObservationBridge(bus=bus, recorder=recorder)
    await bridge.publish(first)
    clock.advance_to(clock.now() + 1)
    second = replace(first, ts_utc=clock.utc_iso(), s_lamports=first.s_lamports + 1)
    await bridge.publish(second)

    published = bus.pending_p2(EventKind.curve_tick, first.mint)
    assert published is not None
    assert published.occurred_at == second.ts_utc
    recorder.seal()
    ticks = load_dataset(tmp_path).events
    assert [tick["S"] for tick in ticks] == [first.s_lamports, second.s_lamports]
    assert [tick["ts_utc"] for tick in ticks] == [first.ts_utc, second.ts_utc]


async def test_out_of_order_observation_is_not_published(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = _observation(clock)
    bus = InspectingBus(clock=clock, events_path=tmp_path / "events.jsonl")
    recorder = LiveRecorder(tmp_path, clock=clock)
    bridge = ObservationBridge(bus=bus, recorder=recorder)
    await bridge.publish(observation)
    old = replace(observation, ts_utc="2025-12-31T23:59:59Z")

    with pytest.raises(ValueError, match="backwards"):
        await bridge.publish(old)
    assert len(bus.bytes_at_publish) == 1
    recorder.seal()
    assert len(load_dataset(tmp_path).events) == 1


class StubBus:
    def __init__(self, order: list[str]) -> None:
        self.events: list[Event] = []
        self._order = order

    async def publish(self, event: Event) -> None:
        self._order.append("bus")
        self.events.append(event)


class OrderedRecorder:
    def __init__(self, order: list[str]) -> None:
        self._order = order
        self.observations: list[CurveObservation] = []

    def record(self, observation: CurveObservation) -> None:
        self._order.append("record")
        self.observations.append(observation)


class OrderedPrice:
    def __init__(self, order: list[str]) -> None:
        self._order = order

    def observe(self, observation: CurveObservation) -> None:
        self._order.append("price")


MARKET_MINT = "MintAAAA1111111111111111111111111111111111"
OCCURRED = "2026-01-01T00:00:00.000000Z"


async def test_market_events_map_to_existing_kinds_with_integer_units() -> None:
    order: list[str] = []
    bus = StubBus(order)
    bridge = ObservationBridge(bus=bus, recorder=OrderedRecorder(order))  # type: ignore[arg-type]
    await bridge.publish_market_event(
        kind=EventKind.trade,
        mint=MARKET_MINT,
        occurred_at=OCCURRED,
        payload={"signature": "S1", "position": 3},
        lamports=1_000,
        token_units=500,
    )
    await bridge.publish_market_event(
        kind=EventKind.token_created,
        mint=MARKET_MINT,
        occurred_at=OCCURRED,
        payload={"signature": "S2"},
    )
    await bridge.publish_market_event(
        kind=EventKind.migration,
        mint=MARKET_MINT,
        occurred_at=OCCURRED,
        payload={"signature": "S3"},
    )
    trade, created, migrated = bus.events
    assert [event.kind for event in bus.events] == [
        EventKind.trade,
        EventKind.token_created,
        EventKind.migration,
    ]
    assert (trade.lamports, trade.token_units) == (1_000, 500)
    assert type(trade.lamports) is int and type(trade.token_units) is int
    assert created.lamports is None and migrated.token_units is None
    assert all(event.entity_id == MARKET_MINT for event in bus.events)
    assert all(event.occurred_at == OCCURRED for event in bus.events)
    assert order == ["bus", "bus", "bus"]


@pytest.mark.parametrize("kind", [EventKind.curve_tick, EventKind.mark, EventKind.kill_switch])
async def test_market_path_refuses_kinds_it_does_not_own(kind: EventKind) -> None:
    order: list[str] = []
    bus = StubBus(order)
    bridge = ObservationBridge(bus=bus, recorder=OrderedRecorder(order))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a market kind"):
        await bridge.publish_market_event(
            kind=kind, mint=MARKET_MINT, occurred_at=OCCURRED, payload={}
        )
    assert bus.events == []
    assert order == []


async def test_market_units_must_be_exact_integers() -> None:
    order: list[str] = []
    bus = StubBus(order)
    bridge = ObservationBridge(bus=bus, recorder=OrderedRecorder(order))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await bridge.publish_market_event(
            kind=EventKind.trade,
            mint=MARKET_MINT,
            occurred_at=OCCURRED,
            payload={},
            lamports=1.5,  # type: ignore[arg-type]
        )
    assert bus.events == []


async def test_observation_is_recorded_then_priced_then_published() -> None:
    clock = FixtureClock(1_767_225_600.0)
    order: list[str] = []
    bridge = ObservationBridge(
        bus=StubBus(order),  # type: ignore[arg-type]
        recorder=OrderedRecorder(order),  # type: ignore[arg-type]
        price=OrderedPrice(order),  # type: ignore[arg-type]
    )
    await bridge.publish(replace(_observation(clock), source="rpc"))
    assert order == ["record", "price", "bus"]


async def test_live_price_source_receives_the_accepted_observation(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    health = SourceSupervisor(clock, random.Random(0), path=tmp_path / "cursor.db")
    health.note_frame()
    prices = LivePriceSource(clock=clock, health=health, max_age_s=10.0, max_observations=4)
    observation = replace(_observation(clock), source="rpc")
    order: list[str] = []
    bridge = ObservationBridge(
        bus=StubBus(order),  # type: ignore[arg-type]
        recorder=OrderedRecorder(order),  # type: ignore[arg-type]
        price=prices,
    )
    await bridge.publish(observation)
    snapshot = await prices.curve(observation.mint)
    assert snapshot is not None
    assert (snapshot.s_lamports, snapshot.t_units) == (observation.s_lamports, observation.t_units)
    assert snapshot.source == "rpc"
    health.close()
