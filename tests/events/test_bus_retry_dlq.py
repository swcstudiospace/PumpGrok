"""Transient retries use the injected RNG and clock. Poison writes one DLQ row."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import (
    BACKOFF_FACTOR,
    BACKOFF_INITIAL_S,
    BACKOFF_JITTER_S,
    BACKOFF_MAX_S,
    RETRY_ATTEMPTS,
)
from pumpgrok.events.dlq import replay
from pumpgrok.events.errors import PoisonEvent, TransientEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

_STEP_S = BACKOFF_MAX_S + BACKOFF_JITTER_S


def _event() -> Event:
    return Event(
        kind=EventKind.trade,
        entity_id="mint",
        payload={"n": 1},
        occurred_at="t1",
    )


def _tick() -> Event:
    return Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": 1},
        occurred_at="t1",
    )


class _Rng:
    def __init__(self) -> None:
        self._rng = make_rng(7)
        self.draws: list[float] = []

    def random(self) -> float:
        value = self._rng.random()
        self.draws.append(value)
        return value


class _SleepLog(FixtureClock):
    """Fake clock that records every retry wait before it advances virtual time."""

    def __init__(self, start: float = 0.0) -> None:
        super().__init__(start)
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        await super().sleep(seconds)


def _expected_delay(step: int, draw: float) -> float:
    base = min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**step, BACKOFF_MAX_S)
    return float(base) + draw * BACKOFF_JITTER_S


async def test_transient_retries_wait_backoff_plus_jitter_on_injected_clock(tmp_path: Path) -> None:
    calls = 0
    rng = _Rng()
    clock = _SleepLog(0.0)

    async def handler(_event: Event) -> None:
        nonlocal calls
        calls += 1
        raise TransientEvent(index=calls)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(tmp_path / "events.sqlite"),
        rng=rng,
    )
    await bus.start()
    await bus.publish(_event())
    await _run_clock(clock, RETRY_ATTEMPTS)
    assert calls == RETRY_ATTEMPTS
    assert len(rng.draws) == RETRY_ATTEMPTS - 1
    assert all(0.0 <= draw < 1.0 for draw in rng.draws)
    assert clock.sleeps == pytest.approx(
        [_expected_delay(step, draw) for step, draw in enumerate(rng.draws)]
    )
    assert _dlq_count(tmp_path / "events.sqlite") == 1


async def test_p2_transient_retries_wait_on_clock_then_writes_one_dlq_row(tmp_path: Path) -> None:
    calls = 0
    clock = _SleepLog(0.0)
    sidecar = tmp_path / "events.sqlite"

    async def handler(_event: Event) -> None:
        nonlocal calls
        calls += 1
        raise TransientEvent(index=calls)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
        rng=make_rng(5),
    )
    await bus.start()
    await bus.publish(_tick())
    await _run_clock(clock, RETRY_ATTEMPTS)
    assert calls == RETRY_ATTEMPTS
    assert len(clock.sleeps) == RETRY_ATTEMPTS - 1
    assert _dlq_count(sidecar) == 1


async def test_poison_writes_one_dlq_row_and_does_not_retry(tmp_path: Path) -> None:
    calls = 0

    async def handler(_event: Event) -> None:
        nonlocal calls
        calls += 1
        raise PoisonEvent(index=0)

    sidecar = tmp_path / "events.sqlite"
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
        rng=make_rng(3),
    )
    await bus.start()
    await bus.publish(_event())
    await _settle()
    assert calls == 1
    assert _dlq_count(sidecar) == 1


async def test_failed_recover_keeps_dlq_row_replayable_and_runs_once(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    event = _event()
    parked = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await parked.publish(event)
    await parked.shutdown()

    async def poison(_event: Event) -> None:
        raise PoisonEvent(index=0)

    failing = EventBus(
        clock=FixtureClock(1.0),
        handler=poison,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await failing.recover()
    assert _dlq_count(sidecar) == 1

    store = EventStore(sidecar)
    assert replay(store, event.event_id) is not None
    store.close()

    delivered: list[str] = []

    async def handler(item: Event) -> None:
        delivered.append(item.event_id)

    recovered = EventBus(
        clock=FixtureClock(2.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [event.event_id]
    await recovered.recover()
    assert delivered == [event.event_id]


def _dlq_count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT COUNT(*) FROM dlq").fetchone()
    assert row is not None
    return int(row[0])


async def _run_clock(clock: _SleepLog, steps: int) -> None:
    """Let each retry reach its wait, then move virtual time past the longest possible wait."""
    for _ in range(steps):
        await _settle()
        clock.advance_to(clock.now() + _STEP_S)
    await _settle()


async def _settle() -> None:
    for _ in range(8):
        await asyncio.sleep(0)


async def _unused(_event: Event) -> None:
    return None
