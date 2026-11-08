"""P2 retries release the key lock during backoff. A superseded retry goes to the DLQ."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import BACKOFF_INITIAL_S, BACKOFF_JITTER_S
from pumpgrok.events.errors import TransientEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


def _tick(n: int) -> Event:
    return Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": n},
        occurred_at=f"t{n}",
    )


async def _settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def _dlq_rows(path: Path) -> list[tuple[str, str]]:
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute("SELECT event_id, reason FROM dlq ORDER BY event_id").fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


async def _supersede(
    sidecar: Path, clock: FixtureClock, dlq_calls: list[str]
) -> tuple[list[int], Event]:
    """Fail tick 1 once, then publish tick 2 while tick 1 sleeps in its backoff."""
    calls: list[int] = []

    async def handler(event: Event) -> None:
        n = int(event.payload["n"])
        calls.append(n)
        if n == 1 and calls.count(1) == 1:
            raise TransientEvent(index=1)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda event: dlq_calls.append(event.event_id),
        store=EventStore(sidecar),
        rng=make_rng(11),
    )
    await bus.start()
    stale = _tick(1)
    await bus.publish(stale)
    await _settle()
    assert calls == [1]
    await bus.publish(_tick(2))
    await _settle()
    return calls, stale


async def test_newer_p2_value_is_delivered_while_stale_retry_sleeps(tmp_path: Path) -> None:
    clock = FixtureClock(0.0)
    dlq_calls: list[str] = []
    calls, _stale = await _supersede(tmp_path / "events.sqlite", clock, dlq_calls)

    # The newer value ran while the stale retry was still in its backoff sleep.
    assert calls == [1, 2]
    assert clock.now() == 0.0
    assert dlq_calls == []


async def test_superseded_stale_retry_is_sent_to_dlq_with_reason_transient(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    clock = FixtureClock(0.0)
    dlq_calls: list[str] = []
    calls, stale = await _supersede(sidecar, clock, dlq_calls)

    clock.advance_to(BACKOFF_INITIAL_S + BACKOFF_JITTER_S)
    await _settle()

    # The stale retry never ran the handler again. It was sent to the DLQ instead.
    assert calls == [1, 2]
    assert dlq_calls == [stale.event_id]
    assert _dlq_rows(sidecar) == [(stale.event_id, "transient")]
