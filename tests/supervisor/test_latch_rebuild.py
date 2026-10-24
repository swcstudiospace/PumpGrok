"""F2: an exhausted seat stays latched across a process restart.

The observe-only latch lives in memory. On construction a ``SeatTask`` rebuilds it from the
newest unresumed ``bot_restart_exhausted`` escalation in the ledger, so a restarted process does
not run the exhausted seat again. A human resume note after that escalation releases it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.seat_task import (
    KIND_HEARTBEAT_STALE,
    KIND_RESTART_EXHAUSTED,
    ObserveOnly,
    SeatTask,
    append_escalation,
)

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
SEAT = "bot-04-sniper"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


async def _ok(ctx: Any) -> dict[str, Any]:
    return {"ok": True}


def _task(
    store: LedgerStore, clock: FixtureClock, latch: ObserveOnly, seat: str = SEAT
) -> SeatTask:
    return SeatTask(
        seat,
        60.0,
        _ok,
        clock=clock,
        rng=make_rng(11),
        store=store,
        source="replay",
        correlation_id="desk",
        observe_only=latch,
    )


def _escalate(store: LedgerStore, clock: FixtureClock, kind: str, seat: str) -> None:
    append_escalation(
        store,
        clock,
        kind=kind,
        seat=seat,
        detail=f"{seat} {kind}",
        source="replay",
        correlation_id="desk",
    )


def _resume(store: LedgerStore, clock: FixtureClock, seat: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="replay",
        correlation_id="desk",
        idempotency_key=f"journal|resume|{seat}|{clock.now():.0f}",
        type="JournalNote",
        payload={
            "source": "replay",
            "note_kind": "note",
            "seat": seat,
            "text": f"resume {seat} by human:alice",
        },
    )


def test_ledger_exhaustion_escalation_latches_the_seat_on_construction(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, SEAT)

    latch = ObserveOnly()
    _task(store, clock, latch)

    assert latch.is_latched(SEAT) is True
    assert latch.reason(SEAT) == KIND_RESTART_EXHAUSTED


def test_resume_note_after_the_exhaustion_escalation_leaves_the_seat_live(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, SEAT)
    clock.advance_to(START + 10.0)
    _resume(store, clock, SEAT)

    latch = ObserveOnly()
    _task(store, clock, latch)

    assert latch.is_latched(SEAT) is False


def test_other_escalations_and_other_seats_do_not_latch(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _escalate(store, clock, KIND_HEARTBEAT_STALE, SEAT)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, "bot-02-risk")

    latch = ObserveOnly()
    _task(store, clock, latch, seat=SEAT)

    assert latch.is_latched(SEAT) is False
    assert latch.seats() == frozenset()


def test_a_new_exhaustion_after_a_resume_latches_again(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, SEAT)
    clock.advance_to(START + 10.0)
    _resume(store, clock, SEAT)
    clock.advance_to(START + 20.0)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, SEAT)

    latch = ObserveOnly()
    _task(store, clock, latch)

    assert latch.is_latched(SEAT) is True


def test_restored_exit_latch_appends_the_halt_before_any_cycle(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _escalate(store, clock, KIND_RESTART_EXHAUSTED, "bot-06-exit")

    _task(store, clock, ObserveOnly(), seat="bot-06-exit")

    halts = store.read(types=["HaltSet"], limit=None)
    assert [row["payload"]["detail"] for row in halts] == ["exit seat observe-only"]
