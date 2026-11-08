"""Transient retries use the injected RNG. Poison writes one DLQ row."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import RETRY_ATTEMPTS
from pumpgrok.events.errors import PoisonEvent, TransientEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


def _event() -> Event:
    return Event(
        kind=EventKind.trade,
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


async def test_transient_retries_with_injected_jitter_and_no_host_sleep(tmp_path: Path) -> None:
    calls = 0
    rng = _Rng()

    async def handler(_event: Event) -> None:
        nonlocal calls
        calls += 1
        raise TransientEvent(index=calls)

    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(tmp_path / "events.sqlite"),
        rng=rng,
    )
    await bus.start()
    await bus.publish(_event())
    await _settle()
    assert calls == RETRY_ATTEMPTS
    assert len(rng.draws) == RETRY_ATTEMPTS - 1
    assert all(0.0 <= draw < 1.0 for draw in rng.draws)
    assert _dlq_count(tmp_path / "events.sqlite") == 1


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


def _dlq_count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT COUNT(*) FROM dlq").fetchone()
    assert row is not None
    return int(row[0])


async def _settle() -> None:
    for _ in range(8):
        await asyncio.sleep(0)
