# Offline tracer: validated observations are recorded before publication.

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
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
