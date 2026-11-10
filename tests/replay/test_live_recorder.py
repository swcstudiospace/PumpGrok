# A sealed observation dataset is verified by the real replay loader.

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pumpgrok.datafeed.bridge import ObservationBridge
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import CorruptFixture, load_dataset
from pumpgrok.replay.live_recorder import LiveRecorder


async def _handle(_event: Event) -> None:
    pass


async def test_recorded_observation_seals_as_one_verified_replay_tick(tmp_path: Path) -> None:
    clock = FixtureClock(1_767_225_600.0)
    observation = CurveObservation(
        mint="MintAAAA1111111111111111111111111111111111",
        ts_utc=clock.utc_iso(),
        s_lamports=42_000_000_000,
        t_units=764_608_076_000_000,
        complete=False,
        source="fixture-rpc",
    )
    bus = EventBus(clock=clock, handler=_handle, dlq=lambda _event: None)
    recorder = LiveRecorder(tmp_path, clock=clock)
    bridge = ObservationBridge(bus=bus, recorder=recorder)

    await bridge.publish(observation)
    assert bus.pending_p2(EventKind.curve_tick, observation.mint) is not None
    recorder.seal()
    dataset = load_dataset(tmp_path)

    assert len(dataset.events) == 1
    assert dataset.events[0] == {
        "kind": "tick",
        "mint": observation.mint,
        "ts_utc": observation.ts_utc,
        "S": observation.s_lamports,
        "T": observation.t_units,
        "complete": observation.complete,
        "source": observation.source,
    }
    assert type(dataset.events[0]["S"]) is int
    assert type(dataset.events[0]["T"]) is int
    events_path = tmp_path / "events.jsonl"
    assert dataset.manifest.sha256["events.jsonl"] == hashlib.sha256(
        events_path.read_bytes()
    ).hexdigest()

    with events_path.open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(CorruptFixture):
        load_dataset(tmp_path)
