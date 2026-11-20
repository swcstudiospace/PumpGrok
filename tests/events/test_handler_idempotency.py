"""Same derived id appends once. Different occurred_at values both append."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock


def _kill(occurred_at: str) -> Event:
    return Event(
        kind=EventKind.kill_switch,
        entity_id="desk",
        payload={"reason": "daily_loss"},
        occurred_at=occurred_at,
    )


async def test_duplicate_id_does_not_append_and_distinct_occurred_at_does(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    ledger_path = tmp_path / "ledger.sqlite"
    assert sidecar != ledger_path
    ledger = LedgerStore(ledger_path)
    calls: list[str] = []

    def append(event: Event) -> None:
        calls.append(event.event_id)
        ledger.append(
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="corr-1",
            idempotency_key=event.event_id,
            type="KillSwitchSet",
            payload={
                "source": "paper",
                "origin": "tool",
                "reason": "daily_loss",
            },
        )

    async def handler(event: Event) -> None:
        append(event)

    first = _kill("2026-01-01T00:00:01Z")
    second = _kill("2026-01-01T00:00:02Z")
    assert first.event_id != second.event_id
    assert first.payload == {"reason": "daily_loss"}
    assert second.payload == {"reason": "daily_loss"}

    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await bus.start()
    await bus.publish(first)
    await bus.publish(first)
    await bus.publish(second)
    await _settle()
    assert calls == [first.event_id, second.event_id]
    assert _row_count(ledger_path) == 2

    await bus.publish(first)
    await _settle()
    assert calls == [first.event_id, second.event_id]
    assert _row_count(ledger_path) == 2


def _row_count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT COUNT(*) FROM events").fetchone()
    assert row is not None
    return int(row[0])


async def _settle() -> None:
    for _ in range(8):
        await asyncio.sleep(0)
