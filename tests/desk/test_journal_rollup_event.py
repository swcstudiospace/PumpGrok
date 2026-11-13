"""Journal rollup follows the reviewed 300 s timer or a position close (EVT-10, 14-04 slice B).

The rollup is the daily report rendered by ``render_report`` from the ledger. It runs on the
journal's 300 s timer (``EVENT_TIMERS``) and on a ``position_closed`` event, which changes realised
P&L. A trade or an open writes a journal note and does not roll up. Events go through the real
EventBus; the timer is driven by the injected FixtureClock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pumpgrok.events.bus import EventBus
from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.scheduler.degraded import DegradedState
from pumpgrok.supervisor.scheduler.event_cycles_aux import build_aux_event_cycles
from pumpgrok.supervisor.scheduler.wake import EVENT_TIMERS
from pumpgrok.supervisor.seat_task import SeatContext
from pumpgrok.tools.journal.render_report import report_path_for

JOURNAL = "bot-09-journal"
TICK_A = "2026-01-01T00:00:01.250Z"
DAY = "2026-01-01"
T0 = parse_ts_utc(TICK_A)


@dataclass
class Harness:
    store: LedgerStore
    clock: FixtureClock
    supervisor: Supervisor
    bus: EventBus
    reports_dir: Path
    runs: list[dict[str, Any]] = field(default_factory=list)
    dlq: list[Event] = field(default_factory=list)


async def _record(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


async def _open(tmp_path: Path) -> Harness:
    clock = FixtureClock(start=T0)
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    reports_dir = tmp_path / "reports"
    runs: list[dict[str, Any]] = []
    body = build_aux_event_cycles(
        store=store,
        degraded=DegradedState(),
        rpc=None,
        replay_llm=None,
        dataset_name="none",
        dataset_events=[],
        trading=None,
        journal_dir=tmp_path / "journal",
        reports_dir=reports_dir,
    )[JOURNAL]

    async def _journal(ctx: SeatContext) -> dict[str, Any]:
        result = await body(ctx)
        runs.append(dict(result or {}))
        return dict(result or {})

    cycles: dict[str, Any] = dict.fromkeys(ROSTER, _record)
    cycles[JOURNAL] = _journal
    supervisor = Supervisor(
        store=store,
        clock=clock,
        rng=make_rng(7),
        cycles=cycles,
        wake_mode="event",
    )
    dlq: list[Event] = []
    bus = EventBus(clock=clock, handler=supervisor.on_event, dlq=dlq.append)
    await bus.start()
    return Harness(store, clock, supervisor, bus, reports_dir, runs, dlq)


async def _close(h: Harness) -> None:
    await h.bus.shutdown()
    h.store.close()


async def _yield(rounds: int = 20) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _settle(done: Callable[[], bool]) -> None:
    for _ in range(100_000):
        if done():
            return
        await asyncio.sleep(0)
    raise AssertionError("event delivery did not settle")


async def _deliver(h: Harness, kind: EventKind) -> dict[str, Any]:
    """Publish one event through the bus and return the journal result it produced."""
    before = len(h.runs)
    event = Event(
        kind=kind,
        entity_id="SmokeMintAAAA1111111111111111111111111111111",
        payload=FrozenPayload({"n": 1}),
        occurred_at=TICK_A,
    )
    await h.bus.publish(event)
    await _yield()
    await _settle(lambda: len(h.runs) > before)
    await _yield()
    return h.runs[-1]


def test_journal_timer_is_the_reviewed_300_seconds() -> None:
    assert EVENT_TIMERS[JOURNAL] == 300.0


async def test_the_timer_rolls_up_at_300_seconds_and_not_before(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        assert JOURNAL in await h.supervisor.tick_once()
        report = report_path_for(h.reports_dir, "daily", DAY)
        assert report.is_file()
        assert h.runs[-1]["rollup"] == str(report)
        assert h.runs[-1]["trigger"] == "timer"

        h.clock.advance_to(T0 + 299.0)
        assert JOURNAL not in await h.supervisor.tick_once()
        assert len(h.runs) == 1

        h.clock.advance_to(T0 + 300.0)
        assert JOURNAL in await h.supervisor.tick_once()
        assert len(h.runs) == 2
        assert h.dlq == []
    finally:
        await _close(h)


async def test_a_position_close_rolls_up_on_the_event_without_the_timer(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        result = await _deliver(h, EventKind.position_closed)
        report = report_path_for(h.reports_dir, "daily", DAY)
        assert report.is_file()
        assert result["rollup"] == str(report)
        assert result["trigger"] == EventKind.position_closed.value
        assert h.dlq == []
    finally:
        await _close(h)


async def test_a_trade_notes_the_journal_but_does_not_roll_up(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        result = await _deliver(h, EventKind.trade)
        assert result["rollup"] is None
        assert result["noted"] is True
        assert not h.reports_dir.exists()
    finally:
        await _close(h)


async def test_the_report_day_comes_from_the_injected_clock(tmp_path: Path) -> None:
    h = await _open(tmp_path)
    try:
        h.clock.advance_to(parse_ts_utc("2026-03-04T12:00:00.000Z"))
        result = await _deliver(h, EventKind.position_closed)
        assert result["rollup"] == str(report_path_for(h.reports_dir, "daily", "2026-03-04"))
        assert Path(str(result["rollup"])).is_file()
    finally:
        await _close(h)
