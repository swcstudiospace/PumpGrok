"""Clock and seeded-RNG contracts (paper-engine.md 4.2, R27)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.replay import (
    DEFAULT_SEED,
    FixtureClock,
    WallClock,
    load_dataset,
    make_rng,
)
from pumpgrok.replay.fixtures import event_epoch

SMOKE = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke"


async def test_fixture_clock_replays_fixture_timestamps_in_order() -> None:
    dataset = load_dataset(SMOKE)
    clock = FixtureClock()
    seen = []
    for event in dataset.events:
        clock.advance_to(event_epoch(event))
        seen.append(clock.now())
    assert seen == [event_epoch(event) for event in dataset.events]
    assert seen == sorted(seen)


def test_fixture_clock_refuses_to_move_backwards() -> None:
    clock = FixtureClock(start=100.0)
    clock.advance_to(100.0)
    with pytest.raises(ValueError, match="backwards"):
        clock.advance_to(99.0)


async def test_wall_clock_advances_monotonically() -> None:
    clock = WallClock()
    first = clock.monotonic()
    await clock.sleep(0.01)
    second = clock.monotonic()
    assert second >= first + 0.005
    assert clock.now() <= time.time() + 1.0


async def test_fixture_sleep_wakes_only_when_virtual_time_reaches_deadline() -> None:
    clock = FixtureClock(start=10.0)
    task = asyncio.create_task(clock.sleep(5.0))
    await asyncio.sleep(0)
    clock.advance_to(14.0)
    await asyncio.sleep(0)
    assert not task.done()
    clock.advance_to(15.0)
    await task
    assert clock.now() == 15.0


async def test_fixture_timeout_cancels_body_at_virtual_deadline() -> None:
    clock = FixtureClock(start=100.0)

    async def body() -> None:
        async with clock.timeout(5.0):
            await clock.sleep(10.0)

    task = asyncio.create_task(body())
    await asyncio.sleep(0)
    clock.advance_to(104.0)
    await asyncio.sleep(0)
    assert not task.done()
    clock.advance_to(105.0)
    with pytest.raises(TimeoutError):
        await task


async def test_fixture_timeout_does_not_fire_after_body_completes() -> None:
    clock = FixtureClock(start=0.0)

    async def body() -> str:
        async with clock.timeout(5.0):
            await clock.sleep(1.0)
        return "done"

    task = asyncio.create_task(body())
    await asyncio.sleep(0)
    clock.advance_to(1.0)
    assert await task == "done"
    clock.advance_to(50.0)  # the stale deadline must not cancel anything now


def test_default_seed_is_the_documented_constant() -> None:
    assert DEFAULT_SEED == 20260101
    assert [make_rng().random() for _ in range(5)] == [
        make_rng(20260101).random() for _ in range(5)
    ]


def test_same_seed_replays_identical_sequence() -> None:
    first = make_rng(42)
    second = make_rng(42)
    assert [first.getrandbits(64) for _ in range(8)] == [second.getrandbits(64) for _ in range(8)]


def test_different_seeds_differ() -> None:
    assert make_rng(1).getrandbits(64) != make_rng(2).getrandbits(64)


def test_replayed_ids_are_byte_identical_for_same_fixture_and_seed() -> None:
    dataset = load_dataset(SMOKE)

    def run() -> list[str]:
        clock = FixtureClock()
        ids = IdFactory(clock, make_rng())
        out = []
        for event in dataset.events:
            clock.advance_to(event_epoch(event))
            out.append(ids.ulid())
        return out

    first = run()
    assert first == run()
    assert first == sorted(first)
