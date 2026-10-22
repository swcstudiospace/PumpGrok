"""Regression tests for Greptile findings 15 and 30 (seat_task.py).

15: a resume note written before a latch must not clear that latch; only a
    resume appended after the latch was set does.
30: an exhausted seat escalates on the rising edge only, not on every later
    failed cycle while it stays latched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.seat_task import (
    KIND_RESTART_EXHAUSTED,
    ObserveOnly,
    RestartPolicy,
    SeatContext,
    SeatTask,
)

SEAT = "bot-01-scout"


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("source", "paper")
    return store


async def _boom(ctx: SeatContext) -> dict[str, Any]:
    raise RuntimeError("seat broke")


class _Notifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


def _ctx(store: LedgerStore, clock: FixtureClock, seat: str) -> SeatContext:
    return SeatContext(seat_id=seat, clock=clock, rng=make_rng(3), store=store)


def _append_resume(store: LedgerStore, clock: FixtureClock, seat: str, label: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="desk",
        idempotency_key=f"resume|{seat}|{label}",
        type="JournalNote",
        payload={
            "source": "paper",
            "seat": seat,
            "note_kind": "note",
            "text": f"resume {seat} by human:alice",
            "refs": [],
        },
    )


def _exhausted_task(
    store: LedgerStore,
    clock: FixtureClock,
    latch: ObserveOnly,
    notifier: Any = None,
) -> SeatTask:
    return SeatTask(
        SEAT,
        10.0,
        _boom,
        clock=clock,
        rng=make_rng(11),
        store=store,
        notifier=notifier,
        observe_only=latch,
        policy=RestartPolicy(capacity=0),
    )


# -- finding 15: old resume notes do not clear new latches ---------------------


async def test_resume_written_before_latch_does_not_clear_it(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        # A human resumed this seat long ago; the note predates the coming latch.
        _append_resume(store, clock, SEAT, "old")
        latch = ObserveOnly()
        task = _exhausted_task(store, clock, latch)
        assert await task.run_guarded(_ctx(store, clock, SEAT)) == "crash"
        assert latch.is_latched(SEAT)

        assert latch.fold_resume(store) == []
        assert latch.is_latched(SEAT)

        clock.advance_to(clock.now() + 5.0)
        _append_resume(store, clock, SEAT, "new")
        assert latch.fold_resume(store) == [SEAT]
        assert not latch.is_latched(SEAT)
    finally:
        store.close()


async def test_resume_after_latch_clears_it_and_only_once(tmp_path: Path) -> None:
    """A resume appended after the latch clears it; replaying the fold keeps it clear."""
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = _exhausted_task(store, clock, latch)
        await task.run_guarded(_ctx(store, clock, SEAT))
        _append_resume(store, clock, SEAT, "first")
        assert latch.fold_resume(store) == [SEAT]
        assert latch.fold_resume(store) == []
    finally:
        store.close()


# -- finding 30: escalation is edge-triggered on the latch ---------------------


async def test_persistent_failure_escalates_once_while_latched(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    notifier: Any = _Notifier()
    try:
        latch = ObserveOnly()
        task = SeatTask(
            SEAT,
            10.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            notifier=notifier,
            observe_only=latch,
        )
        # Six crashes exhaust the 5-per-hour budget; four more fail while latched.
        for _ in range(10):
            assert await task.run_guarded(_ctx(store, clock, SEAT)) == "crash"
            clock.advance_to(clock.now() + 2.0)
        assert latch.is_latched(SEAT)
        rows = store.read(types=["Escalation"], limit=None)
        assert [row["payload"]["kind"] for row in rows] == [KIND_RESTART_EXHAUSTED]
        assert [call["kind"] for call in notifier.sent] == [KIND_RESTART_EXHAUSTED]
        assert len(store.read(types=["HaltSet"], limit=None)) == 0
    finally:
        store.close()


async def test_escalates_again_only_after_a_resume_clears_the_latch(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    notifier: Any = _Notifier()
    try:
        latch = ObserveOnly()
        task = _exhausted_task(store, clock, latch, notifier)
        ctx = _ctx(store, clock, SEAT)
        await task.run_guarded(ctx)
        await task.run_guarded(ctx)
        assert len(store.read(types=["Escalation"], limit=None)) == 1

        clock.advance_to(clock.now() + 5.0)
        _append_resume(store, clock, SEAT, "clear")
        assert latch.fold_resume(store) == [SEAT]

        clock.advance_to(clock.now() + 5.0)
        await task.run_guarded(ctx)
        assert latch.is_latched(SEAT)
        assert len(store.read(types=["Escalation"], limit=None)) == 2
        assert len(notifier.sent) == 2
    finally:
        store.close()
