"""Regression tests for Greptile findings 15 and 30 (seat_task.py).

15: a resume note written before a latch must not clear that latch; only a
    resume appended after the latch was set does.
30: an exhausted seat escalates on the rising edge only, not on every later
    failed cycle while it stays latched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
    # Fail-closed contract (INT-02): the exit halt records this equity.
    store.set_meta("initial_equity_lamports", "10000000000")
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


# -- round 3 finding 2: EXIT retries its protective halt -------------------------

EXIT = "bot-06-exit"


def _fail_once(monkeypatch: pytest.MonkeyPatch, store: LedgerStore, row_type: str) -> None:
    """Make the first ``row_type`` append raise, then behave normally."""
    real_append = store.append
    armed = [True]

    def _append(**kwargs: Any) -> dict[str, Any]:
        if armed[0] and kwargs.get("type") == row_type:
            armed[0] = False
            raise RuntimeError(f"ledger write failed for {row_type}")
        return real_append(**kwargs)

    monkeypatch.setattr(store, "append", _append)


def _exit_task(latch: ObserveOnly, clock: FixtureClock, store: LedgerStore) -> SeatTask:
    return SeatTask(
        EXIT,
        15.0,
        _boom,
        clock=clock,
        rng=make_rng(11),
        store=store,
        observe_only=latch,
        policy=RestartPolicy(capacity=0),
    )


async def test_exit_halt_retried_after_its_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed HaltSet write must be retried on the next failed EXIT cycle."""
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        _fail_once(monkeypatch, store, "HaltSet")
        latch = ObserveOnly()
        task = _exit_task(latch, clock, store)
        assert await task.run_guarded(_ctx(store, clock, EXIT)) == "crash"
        assert latch.is_latched(EXIT)
        assert store.read(types=["HaltSet"], limit=None) == []

        clock.advance_to(clock.now() + 15.0)
        assert await task.run_guarded(_ctx(store, clock, EXIT)) == "crash"
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        assert halts[0]["payload"]["reason"] == "manual"
        assert len(store.read(types=["Escalation"], limit=None)) == 1
    finally:
        store.close()


async def test_exit_halt_written_even_when_escalation_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The protective halt must not depend on the escalation row landing first."""
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        _fail_once(monkeypatch, store, "Escalation")
        latch = ObserveOnly()
        task = _exit_task(latch, clock, store)
        with pytest.raises(RuntimeError, match="ledger write failed for Escalation"):
            await task.run_guarded(_ctx(store, clock, EXIT))
        assert latch.is_latched(EXIT)
        assert len(store.read(types=["HaltSet"], limit=None)) == 1
    finally:
        store.close()


async def test_exit_halt_not_duplicated_on_repeated_failures(tmp_path: Path) -> None:
    """Retrying while latched is idempotent: one HaltSet per UTC day."""
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = _exit_task(latch, clock, store)
        for _ in range(4):
            assert await task.run_guarded(_ctx(store, clock, EXIT)) == "crash"
            clock.advance_to(clock.now() + 15.0)
        assert len(store.read(types=["HaltSet"], limit=None)) == 1
        assert len(store.read(types=["Escalation"], limit=None)) == 1
    finally:
        store.close()
