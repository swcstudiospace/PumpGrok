"""Sidecar dedup survives reopen and expires only on the injected clock."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.config.sections.v4 import EventsSettings
from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import (
    EVENTS_SIDECAR_PATH,
    P0_DEDUP_TTL_S,
    P1_DEDUP_TTL_S,
    P2_DEBOUNCE_S,
)
from pumpgrok.events.errors import SidecarRefusal
from pumpgrok.events.models import Event, EventKind
from pumpgrok.events.store import EventStore
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.replay.clock import FixtureClock


def _event(kind: EventKind, occurred_at: str, entity_id: str = "mint") -> Event:
    return Event(
        kind=kind,
        entity_id=entity_id,
        payload={"n": occurred_at},
        occurred_at=occurred_at,
    )


def test_settings_sidecar_default_matches_constant() -> None:
    assert EventsSettings().sidecar_path == str(EVENTS_SIDECAR_PATH)


def test_store_refuses_paper_ledger_before_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    paper = PAPER_LEDGER_PATH
    with pytest.raises(SidecarRefusal, match="PAPER_LEDGER_PATH") as raised:
        EventStore(paper)
    assert str(paper) in str(raised.value)
    assert "payload" not in str(raised.value)
    assert not paper.exists()
    assert not paper.with_name(paper.name + "-wal").exists()


def test_importing_events_does_not_open_sqlite() -> None:
    import pumpgrok.events as events  # noqa: PLC0415 - import side effect is the assertion

    assert events.__doc__
    source = Path(events.__file__).read_text(encoding="utf-8")
    assert "sqlite3" not in source
    assert "LedgerStore" not in source


async def test_p0_and_p1_dedup_survive_reopen_until_named_ttl(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    clock = FixtureClock(10.0)
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    p0 = _event(EventKind.kill_switch, "t0", "desk")
    p1 = _event(EventKind.trade, "t1", "mint")
    bus = EventBus(clock=clock, handler=handler, dlq=lambda _event: None, store=EventStore(sidecar))
    await bus.start()
    await bus.publish(p0)
    await bus.publish(p1)
    await _drain()
    assert delivered == [p0.event_id, p1.event_id]

    reopened = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await reopened.start()
    await reopened.publish(p0)
    await reopened.publish(p1)
    await _drain()
    assert delivered == [p0.event_id, p1.event_id]

    clock.advance_to(10.0 + P1_DEDUP_TTL_S)
    await reopened.publish(p1)
    await reopened.publish(p0)
    await _drain()
    assert p1.event_id in delivered[2:]
    assert p0.event_id not in delivered[2:]

    clock.advance_to(10.0 + P0_DEDUP_TTL_S)
    await reopened.publish(p0)
    await _drain()
    assert delivered[-1] == p0.event_id


async def test_two_marks_inside_debounce_deliver_latest(tmp_path: Path) -> None:
    clock = FixtureClock(0.0)
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.occurred_at)

    bus = EventBus(
        clock=clock,
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(tmp_path / "events.sqlite"),
    )
    await bus.start()
    await bus.publish(_event(EventKind.mark, "m1"))
    await bus.publish(_event(EventKind.mark, "m2"))
    await _drain()
    clock.advance_to(P2_DEBOUNCE_S)
    await _drain()
    assert delivered == ["m2"]


def test_sidecar_tables_exclude_events_and_hash_chain(tmp_path: Path) -> None:
    path = tmp_path / "events.sqlite"
    EventStore(path)
    with sqlite3.connect(path) as db:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names == {"pending", "applied", "dedup", "dlq", "cursors", "meta"}
    assert "events" not in names


async def _drain() -> None:
    for _ in range(5):
        await asyncio.sleep(0)
