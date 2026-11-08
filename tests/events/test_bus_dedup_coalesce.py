"""Sidecar dedup survives reopen and expires only on the injected clock."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from pumpgrok.config.sections.v4 import EventsSettings
from pumpgrok.events import bus as bus_module
from pumpgrok.events.bus import EventBus
from pumpgrok.events.constants import (
    EVENTS_SIDECAR_PATH,
    P0_DEDUP_TTL_S,
    P1_DEDUP_TTL_S,
    P2_DEBOUNCE_S,
)
from pumpgrok.events.dlq import replay
from pumpgrok.events.errors import PoisonEvent, SidecarRefusal
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


def _tick(n: int) -> Event:
    return Event(
        kind=EventKind.curve_tick,
        entity_id="mint",
        payload={"n": n},
        occurred_at=f"t{n}",
    )


async def _spin() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


def _dlq_count(path: Path) -> int:
    with sqlite3.connect(path) as db:
        row = db.execute("SELECT COUNT(*) FROM dlq").fetchone()
    assert row is not None
    return int(row[0])


async def _unused(_event: Event) -> None:
    return None


async def test_overflowed_p1_event_is_deduplicated_and_replays_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(bus_module._LANE_CAP, 1, 1)
    sidecar = tmp_path / "events.sqlite"
    store = EventStore(sidecar)
    dlq_calls: list[str] = []

    def dlq(event: Event) -> None:
        dlq_calls.append(event.event_id)

    queued = _event(EventKind.trade, "t1", "mint")
    overflow = _event(EventKind.trade, "t2", "mint")
    bus = EventBus(clock=FixtureClock(0.0), handler=_unused, dlq=dlq, store=store)
    await bus.publish(queued)
    await bus.publish(overflow)
    await bus.publish(overflow)
    assert dlq_calls == [overflow.event_id]
    assert bus.queued(1) == 1

    assert replay(store, overflow.event_id) is not None
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    recovered = EventBus(
        clock=FixtureClock(1.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(sidecar),
    )
    await recovered.recover()
    assert delivered == [overflow.event_id]
    await recovered.recover()
    assert delivered == [overflow.event_id]


async def test_running_p2_handler_is_not_cancelled_and_newest_value_runs_once(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    gate = asyncio.Event()
    calls: list[int] = []
    completed: list[int] = []

    async def handler(event: Event) -> None:
        n = int(event.payload["n"])
        calls.append(n)
        if n == 1:
            started.set()
            await gate.wait()
        completed.append(n)

    bus = EventBus(
        clock=FixtureClock(0.0),
        handler=handler,
        dlq=lambda _event: None,
        store=EventStore(tmp_path / "events.sqlite"),
    )
    await bus.start()
    await bus.publish(_tick(1))
    await started.wait()
    await bus.publish(_tick(2))
    await _spin()
    assert calls == [1]
    assert completed == []
    gate.set()
    await _spin()
    assert completed == [1, 2]
    assert calls == [1, 2]


async def test_p2_poison_goes_to_dlq_instead_of_escaping_its_task(tmp_path: Path) -> None:
    sidecar = tmp_path / "events.sqlite"
    dlq_calls: list[str] = []

    def dlq(event: Event) -> None:
        dlq_calls.append(event.event_id)

    async def handler(_event: Event) -> None:
        raise PoisonEvent(index=0)

    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=dlq, store=EventStore(sidecar))
    tick = _tick(1)
    await bus.start()
    await bus.publish(tick)
    await _spin()
    assert dlq_calls == [tick.event_id]
    assert _dlq_count(sidecar) == 1


async def test_delivered_p2_id_is_removed_from_dedup_state() -> None:
    delivered: list[str] = []

    async def handler(event: Event) -> None:
        delivered.append(event.event_id)

    tick = _tick(1)
    bus = EventBus(clock=FixtureClock(0.0), handler=handler, dlq=lambda _event: None)
    await bus.start()
    await bus.publish(tick)
    await _spin()
    assert delivered == [tick.event_id]
    assert tick.event_id not in bus._seen
