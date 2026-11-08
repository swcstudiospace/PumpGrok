"""Write-ahead accept for P0/P1, one-transaction completion, and P2 persistence rules."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

from pumpgrok.events import bus as bus_module
from pumpgrok.events.bus import EventBus
from pumpgrok.events.errors import PoisonEvent
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.replay.clock import FixtureClock


def _trade(occurred_at: str) -> Event:
    return Event(
        kind=EventKind.trade,
        entity_id="mint",
        payload={"n": occurred_at},
        occurred_at=occurred_at,
    )


def _halt(occurred_at: str) -> Event:
    return Event(
        kind=EventKind.halt,
        entity_id="desk",
        payload={"n": occurred_at},
        occurred_at=occurred_at,
    )


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


@contextmanager
def _db(path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(path)) as db:
        yield db


def _rows(path: Path, sql: str, *params: str) -> int:
    with _db(path) as db:
        row = db.execute(sql, params).fetchone()
    assert row is not None
    return int(row[0])


def _rename(path: Path, old: str, new: str) -> None:
    with closing(sqlite3.connect(path, isolation_level=None)) as db:
        db.execute(f"ALTER TABLE {old} RENAME TO {new}")


async def _unused(_event: Event) -> None:
    return None


async def test_queued_p1_is_written_ahead_as_dedup_and_pending_rows(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.publish(_trade("t1"))
    assert bus.queued(1) == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM dedup") == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM dlq") == 0


async def test_failed_overflow_write_leaves_no_dedup_row_and_retried_publish_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(bus_module._LANE_CAP, 1, 1)
    sidecar = tmp_path / "events.sqlite"
    queued = _trade("t1")
    overflow = _trade("t2")
    dlq_calls: list[str] = []
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda event: dlq_calls.append(event.event_id),
        store=EventStore(sidecar),
    )
    await bus.publish(queued)

    # The overflow transaction writes its dedup row first, then the DLQ row. Break the second.
    _rename(sidecar, "dlq", "dlq_hidden")
    with pytest.raises(sqlite3.OperationalError):
        await bus.publish(overflow)
    _rename(sidecar, "dlq_hidden", "dlq")

    assert dlq_calls == []
    assert bus.queued(1) == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM dedup WHERE event_id = ?", overflow.event_id) == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM dlq") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 1

    await bus.publish(overflow)
    assert dlq_calls == [overflow.event_id]
    assert _rows(sidecar, "SELECT COUNT(*) FROM dedup WHERE event_id = ?", overflow.event_id) == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM dlq WHERE event_id = ?", overflow.event_id) == 1


async def test_p0_success_is_one_transaction_applied_row_and_no_pending_row(
    tmp_path: Path,
) -> None:
    sidecar = tmp_path / "events.sqlite"
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    event = _halt("h1")
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.start()
    await bus.publish(event)
    await _settle()
    assert delivered == [event.event_id]
    assert _rows(sidecar, "SELECT COUNT(*) FROM applied WHERE event_id = ?", event.event_id) == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM dlq") == 0


async def test_p1_poison_is_one_transaction_dlq_row_and_no_pending_row(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"

    async def poison(_event: Event) -> None:
        raise PoisonEvent(index=0)

    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=poison,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.start()
    await bus.publish(_trade("t1"))
    await _settle()
    assert _rows(sidecar, "SELECT COUNT(*) FROM dlq WHERE reason = 'poison'") == 1
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM applied") == 0


async def test_p2_writes_no_pending_row_at_accept(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=_unused,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.publish(_tick(1))
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM dedup") == 0


async def test_p2_success_writes_no_applied_dedup_or_pending_row(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    delivered: list[int] = []

    async def handler(event: Event) -> None:
        delivered.append(int(event.payload["n"]))

    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.start()
    await bus.publish(_tick(1))
    await _settle()
    assert delivered == [1]
    assert _rows(sidecar, "SELECT COUNT(*) FROM applied") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM dedup") == 0
    assert _rows(sidecar, "SELECT COUNT(*) FROM pending") == 0
