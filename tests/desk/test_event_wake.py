"""Event wake matrix and event-mode timers (EVT-10).

The matrix is owner-confirmed. In event mode a seat runs only when a bus event on its row
arrives, or when it is one of the three timers. Cadence mode is unchanged and is covered by
tests/supervisor/test_scheduler.py.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.events.models import Event, EventKind, FrozenPayload
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.scheduler import ROSTER, SEAT_CADENCES, Supervisor
from pumpgrok.supervisor.scheduler.wake import EVENT_TIMERS, SEAT_WAKES, wake_order
from pumpgrok.supervisor.seat_task import SeatContext

CHIEF = "bot-00-chief"
SCOUT = "bot-01-scout"
RISK = "bot-02-risk"
WHALE = "bot-03-whale"
SNIPER = "bot-04-sniper"
RUG = "bot-05-rug"
EXIT = "bot-06-exit"
SHILL = "bot-07-shill"
SIGNAL = "bot-08-signal"
JOURNAL = "bot-09-journal"

# Owner-confirmed rows, written in roster order (delivery order is roster order).
OWNER_MATRIX: dict[EventKind, tuple[str, ...]] = {
    EventKind.kill_switch: (CHIEF, RISK, SNIPER, EXIT, SIGNAL),
    EventKind.halt: (CHIEF, RISK, SNIPER, EXIT, SIGNAL),
    EventKind.exit_signal: (RISK, EXIT),
    EventKind.risk_veto: (CHIEF, RISK, SNIPER),
    EventKind.token_created: (SCOUT, WHALE, SIGNAL),
    EventKind.migration: (SCOUT, WHALE, SIGNAL),
    EventKind.strategy_intent: (RISK, SNIPER),
    EventKind.curve_tick: (RISK, RUG, EXIT),
    EventKind.mark: (RISK, RUG, EXIT),
    EventKind.trade: (CHIEF, EXIT, JOURNAL),
    EventKind.position_opened: (CHIEF, EXIT, JOURNAL),
    EventKind.position_closed: (CHIEF, EXIT, JOURNAL),
}

ORIGINAL_CADENCES: dict[str, float] = {
    CHIEF: 60.0,
    SCOUT: 10.0,
    RISK: 5.0,
    WHALE: 120.0,
    SNIPER: 1.0,
    RUG: 30.0,
    EXIT: 15.0,
    SHILL: 300.0,
    SIGNAL: 1.0,
    JOURNAL: 300.0,
}


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _recording_cycles(log: list[str]) -> dict[str, Any]:
    async def _record(ctx: SeatContext) -> dict[str, Any]:
        log.append(ctx.seat_id)
        return {"ok": True}

    return dict.fromkeys(ROSTER, _record)


def _event(kind: EventKind, entity_id: str = "mint-a", n: int = 1) -> Event:
    return Event(
        kind=kind,
        entity_id=entity_id,
        payload=FrozenPayload({"n": n}),
        occurred_at="2026-01-01T00:00:00.000+00:00",
    )


def test_matrix_matches_owner_confirmed_rows() -> None:
    assert dict(SEAT_WAKES) == OWNER_MATRIX


def test_every_event_kind_has_a_row_and_no_other_key() -> None:
    assert set(SEAT_WAKES) == set(EventKind)


@pytest.mark.parametrize("kind", list(EventKind), ids=lambda kind: kind.value)
def test_wake_order_is_roster_order_with_each_seat_once(kind: EventKind) -> None:
    order = wake_order(kind)
    assert order == OWNER_MATRIX[kind]
    assert len(set(order)) == len(order)
    assert order == tuple(sorted(order, key=ROSTER.index))


def test_matrix_names_only_roster_seats() -> None:
    named = {seat for row in SEAT_WAKES.values() for seat in row}
    assert named <= set(ROSTER)


def test_event_timers_are_exactly_the_three_owner_timers() -> None:
    assert dict(EVENT_TIMERS) == {RISK: 5.0, EXIT: 15.0, JOURNAL: 300.0}


def test_cadence_table_is_unchanged() -> None:
    assert SEAT_CADENCES == ORIGINAL_CADENCES


@pytest.mark.parametrize("kind", list(EventKind), ids=lambda kind: kind.value)
async def test_event_dispatch_wakes_each_row_seat_once_in_roster_order(
    tmp_path: Path, kind: EventKind
) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        outcomes = await supervisor.dispatch(_event(kind))
        assert log == list(OWNER_MATRIX[kind])
        assert list(outcomes) == list(OWNER_MATRIX[kind])
        assert set(outcomes.values()) == {"ok"}
    finally:
        store.close()


async def test_repeated_events_wake_their_rows_again(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        await supervisor.dispatch(_event(EventKind.trade, n=1))
        await supervisor.dispatch(_event(EventKind.trade, n=2))
        assert log == list(OWNER_MATRIX[EventKind.trade]) * 2
    finally:
        store.close()


async def test_only_listed_timers_fire_in_event_mode(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    periods = {RISK: 5, EXIT: 15, JOURNAL: 300}
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        for second in range(0, 301):
            clock.advance_to(float(second))
            before = len(log)
            outcomes = await supervisor.tick_once()
            expected = tuple(
                seat for seat in ROSTER if seat in periods and second % periods[seat] == 0
            )
            assert tuple(outcomes) == expected, second
            assert log[before:] == list(expected), second
    finally:
        store.close()


async def test_event_only_seats_never_go_stale_by_time(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    try:
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_recording_cycles(log),
            wake_mode="event",
        )
        await supervisor.dispatch(_event(EventKind.curve_tick))
        clock.advance_to(10_000.0)
        freshness = supervisor.seat_freshness()
        assert freshness[RUG]["stale"] is False
        assert freshness[CHIEF]["stale"] is False
        assert supervisor.tasks[RUG].stale_cadence_s == math.inf
        assert supervisor.tasks[RISK].stale_cadence_s == 5.0
        assert supervisor.tasks[JOURNAL].stale_cadence_s == 300.0
    finally:
        store.close()


async def test_cadence_mode_is_unchanged_and_refuses_event_dispatch(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    log: list[str] = []
    try:
        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(7), cycles=_recording_cycles(log)
        )
        outcomes = await supervisor.tick_once()
        assert log == list(ROSTER)
        assert list(outcomes) == list(ROSTER)
        with pytest.raises(RuntimeError):
            await supervisor.dispatch(_event(EventKind.trade))
    finally:
        store.close()


def test_unknown_wake_mode_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        with pytest.raises(ValueError):
            Supervisor(
                store=store,
                clock=FixtureClock(start=0.0),
                rng=make_rng(7),
                cycles=_recording_cycles([]),
                wake_mode="live",
            )
    finally:
        store.close()
