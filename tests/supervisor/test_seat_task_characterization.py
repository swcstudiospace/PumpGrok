"""Characterization: seat_task wake, restart and relay behaviour (QLT-04, QLT-05, CONTEXT D-10).

Pins supervisor/seat_task.py on the unsplit code before the 11-09 split. Virtual time only
(FixtureClock, make_rng(11)); no wall clock, no sleep and no skipped test.

- wake: due at start and one cadence after each cycle; cycle timeout max(30, 4 x cadence);
  heartbeat stale after three missed cadences, edge-triggered and re-armed by a clean cycle.
- restart: backoff min(16, 2**n) plus seeded jitter gates not_before; the sixth crash in the
  rolling hour latches observe-only with one escalation; the exit seat writes HaltSet manual.
- relay: tail relay of Escalation, HaltSet, KillSwitchSet, BreakerTripped and LiveWriteAttempted
  to notify.alert; a None notifier only advances the cursor; relay failures never raise.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.seat_relay import (
    CLOCK_SKEW_S,
    ClockSkew,
    append_escalation,
    escalation_severity,
    relay_tail,
)
from pumpgrok.supervisor.seat_restart import (
    BACKOFF_CAP_S,
    RESTART_CAPACITY,
    RESTART_WINDOW_S,
    ObserveOnly,
    RestartPolicy,
)
from pumpgrok.supervisor.seat_task import STALE_CADENCES, SeatContext, SeatTask

BASE = 1_000_000.0
SNIPER = "bot-04-sniper"
EXIT = "bot-06-exit"
SCOUT = "bot-01-scout"
RESTART_HOLD_S = 60.0
EQUITY = 10_000_000_000


class _Notifier:
    """Records every notify.alert send; fails every call when told to."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    async def send(self, **kwargs: Any) -> None:
        if self._fail:
            raise RuntimeError("notify.alert is down")
        self.calls.append(kwargs)


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    return store


def _ctx(store: LedgerStore, clock: FixtureClock, seat: str) -> SeatContext:
    return SeatContext(
        seat_id=seat,
        clock=clock,
        rng=make_rng(11),
        store=store,
        source="paper",
        correlation_id="desk",
    )


def _task(
    seat: str,
    cycle: Any,
    clock: FixtureClock,
    store: LedgerStore,
    *,
    cadence: float = 1.0,
    latch: ObserveOnly | None = None,
    notifier: _Notifier | None = None,
    stale_cadence: float | None = None,
) -> SeatTask:
    return SeatTask(
        seat,
        cadence,
        cycle,
        clock=clock,
        rng=make_rng(11),
        store=store,
        notifier=notifier,
        observe_only=latch,
        stale_cadence_s=stale_cadence,
    )


async def _boom(ctx: SeatContext) -> dict[str, Any]:
    raise RuntimeError("seat crashed")


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


async def _slow(ctx: SeatContext) -> dict[str, Any]:
    await ctx.clock.sleep(100.0)
    return {"ok": True}


def _append(
    store: LedgerStore,
    clock: FixtureClock,
    event_type: str,
    payload: dict[str, Any],
    key: str,
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="desk",
        idempotency_key=key,
        type=event_type,
        payload=payload,
    )


async def _crash_until_exhausted(
    task: SeatTask, store: LedgerStore, clock: FixtureClock, seat: str
) -> float:
    """Crash once per restart slot, then crash the sixth time; return the sixth crash's time."""
    for _ in range(RESTART_CAPACITY):
        assert await task.run_guarded(_ctx(store, clock, seat)) == "crash"
        assert task.not_before is not None
        clock.advance_to(task.not_before + RESTART_HOLD_S)
    sixth_at = clock.now()
    assert await task.run_guarded(_ctx(store, clock, seat)) == "crash"
    return sixth_at


# --- wake: due, timeout and staleness --------------------------------------------------------


async def test_due_at_start_then_one_cadence_after_each_cycle(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _ok, clock, store, cadence=10.0)
        assert task.is_due(BASE) is True
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        assert task.last_started_at == BASE
        assert task.last_finished_at == BASE
        assert (task.cycles, task.crashes, task.last_ok) == (1, 0, True)
        assert task.is_due(BASE + 9.5) is False
        assert task.is_due(BASE + 10.0) is True
    finally:
        store.close()


def test_cycle_timeout_is_max_thirty_seconds_or_four_cadences(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        assert _task(SNIPER, _ok, clock, store, cadence=1.0).timeout_s == 30.0
        assert _task(SNIPER, _ok, clock, store, cadence=10.0).timeout_s == 40.0
        assert _task(SNIPER, _ok, clock, store, cadence=20.0).timeout_s == 80.0
    finally:
        store.close()


async def test_stale_after_three_cadences_and_edge_triggered(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _ok, clock, store, cadence=1.0)
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        assert STALE_CADENCES == 3
        assert task.is_stale(BASE + 3.0) is False
        assert task.is_stale(BASE + 3.5) is True
        clock.advance_to(BASE + 3.5)
        assert await task.check_stale(BASE + 3.5) is True
        assert await task.check_stale(BASE + 4.0) is False
        escalations = store.read(types=["Escalation"], limit=None)
        assert [row["payload"]["kind"] for row in escalations] == ["heartbeat_stale"]
        assert escalations[0]["payload"]["seat"] == SNIPER
        assert escalations[0]["payload"]["detail"] == f"{SNIPER} stale for 3 cadences"
    finally:
        store.close()


async def test_a_clean_cycle_rearms_the_stale_edge(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _ok, clock, store, cadence=1.0)
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        clock.advance_to(BASE + 4.0)
        assert await task.check_stale(BASE + 4.0) is True
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        clock.advance_to(BASE + 8.0)
        assert await task.check_stale(BASE + 8.0) is True
        kinds = [row["payload"]["kind"] for row in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["heartbeat_stale", "heartbeat_stale"]
    finally:
        store.close()


async def test_stale_cadence_override_widens_only_the_grace(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _ok, clock, store, cadence=1.0, stale_cadence=5.0)
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        assert task.is_stale(BASE + 15.0) is False
        assert task.is_stale(BASE + 15.5) is True
    finally:
        store.close()


async def test_cycle_past_its_timeout_counts_as_a_crash(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SCOUT, _slow, clock, store, cadence=1.0)
        run = asyncio.ensure_future(task.run_guarded(_ctx(store, clock, SCOUT)))
        await clock.yield_to_loop()
        clock.advance_to(BASE + 30.0)
        assert await run == "crash"
        assert task.crashes == 1
        assert task.last_ok is False
        assert task.restarts == 1
        assert task.not_before is not None
    finally:
        store.close()


# --- restart: bounded budget, backoff and latch ----------------------------------------------


async def test_backoff_is_min_sixteen_or_two_to_the_n_plus_seeded_jitter(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _boom, clock, store)
        expect_rng = make_rng(11)
        for attempt in range(RESTART_CAPACITY):
            now = clock.now()
            assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "crash"
            expected_wait = min(BACKOFF_CAP_S, 2.0**attempt) + expect_rng.uniform(0.0, 1.0)
            assert task.not_before == now + expected_wait
            assert task.restarts == attempt + 1
            clock.advance_to(task.not_before + RESTART_HOLD_S)
    finally:
        store.close()


async def test_sixth_crash_in_the_hour_latches_with_one_escalation(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = _task(SNIPER, _boom, clock, store, latch=latch)
        await _crash_until_exhausted(task, store, clock, SNIPER)
        assert task.restarts == RESTART_CAPACITY
        assert latch.is_latched(SNIPER) is True
        assert latch.reason(SNIPER) == "bot_restart_exhausted"
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "crash"
        escalations = store.read(types=["Escalation"], limit=None)
        assert len(escalations) == 1
        payload = escalations[0]["payload"]
        assert payload["kind"] == "bot_restart_exhausted"
        assert payload["seat"] == SNIPER
        assert payload["detail"] == f"{SNIPER} restart budget exhausted; observe-only"
    finally:
        store.close()


async def test_exit_seat_exhaustion_writes_one_manual_halt(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        latch = ObserveOnly()
        task = _task(EXIT, _boom, clock, store, latch=latch)
        await _crash_until_exhausted(task, store, clock, EXIT)
        assert latch.is_latched(EXIT) is True
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        payload = halts[0]["payload"]
        assert payload["reason"] == "manual"
        assert payload["detail"] == "exit seat observe-only"
        assert payload["equity_lamports"] == EQUITY
        assert payload["day_start_equity_lamports"] == EQUITY
        assert payload["set_by"] == "risk_engine"
    finally:
        store.close()


def test_restart_budget_is_five_per_rolling_hour() -> None:
    policy = RestartPolicy()
    assert (policy.capacity, policy.window_s) == (RESTART_CAPACITY, RESTART_WINDOW_S)
    for _ in range(RESTART_CAPACITY):
        assert policy.record_crash(0.0) is True
    assert policy.record_crash(0.0) is False
    assert policy.record_crash(RESTART_WINDOW_S) is True


def test_observe_only_latch_keeps_the_first_reason_and_sequence() -> None:
    latch = ObserveOnly()
    latch.latch(SNIPER, "bot_restart_exhausted", after_seq=3)
    latch.latch(SNIPER, "other", after_seq=9)
    assert latch.reason(SNIPER) == "bot_restart_exhausted"
    assert latch.seats() == frozenset({SNIPER})


def test_observe_only_paper_write_matrix() -> None:
    sniper = ObserveOnly()
    sniper.latch(SNIPER, "bot_restart_exhausted")
    assert sniper.paper_write_allowed(SNIPER, "sell") is False
    assert sniper.paper_write_allowed(EXIT, "buy") is False
    assert sniper.paper_write_allowed(EXIT, "sell") is True

    risk = ObserveOnly()
    risk.latch("bot-02-risk", "bot_restart_exhausted")
    assert risk.paper_write_allowed(EXIT, "buy") is False
    assert risk.paper_write_allowed(EXIT, "sell") is True

    exit_seat = ObserveOnly()
    exit_seat.latch(EXIT, "bot_restart_exhausted")
    assert exit_seat.paper_write_allowed(EXIT, "sell") is False


def test_resume_before_the_latch_does_not_clear_it_but_one_after_does(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        note = {
            "source": "paper",
            "seat": SNIPER,
            "note_kind": "note",
            "text": f"resume {SNIPER} by human:alice",
            "refs": [],
        }
        _append(store, clock, "JournalNote", note, "resume-before")
        latch = ObserveOnly()
        latch.latch(SNIPER, "bot_restart_exhausted", after_seq=store.count())
        assert latch.fold_resume(store) == []
        assert latch.is_latched(SNIPER) is True
        _append(store, clock, "JournalNote", note, "resume-after")
        assert latch.fold_resume(store) == [SNIPER]
        assert latch.is_latched(SNIPER) is False
    finally:
        store.close()


# --- relay: escalations and ledger tail to notify.alert --------------------------------------


async def test_exhaustion_relays_one_critical_alert_with_a_seat_keyed_idempotency(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        notifier = _Notifier()
        task = _task(SNIPER, _boom, clock, store, notifier=notifier)
        sixth_at = await _crash_until_exhausted(task, store, clock, SNIPER)
        assert len(notifier.calls) == 1
        call = notifier.calls[0]
        assert call["severity"] == "critical"
        assert call["kind"] == "bot_restart_exhausted"
        assert call["text"] == f"{SNIPER} restart budget exhausted"
        assert call["fields"] == {"seat": SNIPER}
        assert call["idempotency_key"] == (
            f"escalation|bot_restart_exhausted|{SNIPER}|{sixth_at:.0f}"
        )
    finally:
        store.close()


async def test_heartbeat_stale_relays_a_warning(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        notifier = _Notifier()
        task = _task(SNIPER, _ok, clock, store, notifier=notifier)
        assert await task.run_guarded(_ctx(store, clock, SNIPER)) == "ok"
        clock.advance_to(BASE + 3.5)
        assert await task.check_stale(BASE + 3.5) is True
        assert [(c["severity"], c["kind"], c["text"]) for c in notifier.calls] == [
            ("warning", "heartbeat_stale", f"{SNIPER} heartbeat stale")
        ]
    finally:
        store.close()


def test_escalation_severity_vocabulary() -> None:
    assert escalation_severity("bot_restart_exhausted") == "critical"
    assert escalation_severity("persistence_down") == "critical"
    assert escalation_severity("clock_skew") == "critical"
    assert escalation_severity("ledger_inconsistent") == "critical"
    assert escalation_severity("heartbeat_stale") == "warning"
    assert escalation_severity("never_seen_kind") == "warning"


def _halt_payload(detail: str) -> dict[str, Any]:
    return {
        "source": "paper",
        "reason": "manual",
        "detail": detail,
        "equity_lamports": EQUITY,
        "day_start_equity_lamports": EQUITY,
        "set_by": "risk_engine",
    }


def _note_payload(text: str) -> dict[str, Any]:
    return {"source": "paper", "seat": "desk", "note_kind": "note", "text": text, "refs": []}


async def test_tail_relay_maps_each_relayed_type_and_skips_the_rest(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append(
            store,
            clock,
            "Escalation",
            {"source": "paper", "kind": "bot_restart_exhausted", "seat": SNIPER, "detail": "d1"},
            "e1",
        )
        _append(store, clock, "JournalNote", _note_payload("not relayed"), "n1")
        _append(store, clock, "HaltSet", _halt_payload("d3"), "h1")
        _append(
            store,
            clock,
            "KillSwitchSet",
            {"source": "paper", "origin": "env", "reason": "operator"},
            "k1",
        )
        _append(
            store,
            clock,
            "BreakerTripped",
            {
                "source": "paper",
                "breaker": "data_stale",
                "metric": "m",
                "threshold": "t",
                "cooldown_s": 60,
            },
            "b1",
        )
        _append(
            store,
            clock,
            "LiveWriteAttempted",
            {
                "source": "paper",
                "adapter": "pumpfun-bonding-curve",
                "method": "send",
                "caller_seat": SNIPER,
            },
            "l1",
        )
        _append(
            store,
            clock,
            "Escalation",
            {"source": "paper", "kind": "heartbeat_stale", "seat": SNIPER, "detail": "d7"},
            "e2",
        )
        notifier = _Notifier()
        assert await relay_tail(store, notifier, clock, 0) == 7
        assert [(c["severity"], c["kind"], c["text"]) for c in notifier.calls] == [
            ("critical", "bot_restart_exhausted", "Escalation: d1"),
            ("critical", "halt", "HaltSet: d3"),
            ("critical", "killswitch", "KillSwitchSet: "),
            ("critical", "breaker", "BreakerTripped: "),
            ("critical", "escalation", "LiveWriteAttempted: "),
            ("warning", "heartbeat_stale", "Escalation: d7"),
        ]
        assert [c["idempotency_key"] for c in notifier.calls] == [
            "relay|Escalation|1",
            "relay|HaltSet|3",
            "relay|KillSwitchSet|4",
            "relay|BreakerTripped|5",
            "relay|LiveWriteAttempted|6",
            "relay|Escalation|7",
        ]
        assert [c["fields"] for c in notifier.calls] == [{"seq": n} for n in (1, 3, 4, 5, 6, 7)]
    finally:
        store.close()


async def test_tail_relay_cursor_never_resends_and_none_only_advances(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append(store, clock, "HaltSet", _halt_payload("d"), "h1")
        assert await relay_tail(store, None, clock, 0) == 1
        notifier = _Notifier()
        assert await relay_tail(store, notifier, clock, 1) == 1
        assert notifier.calls == []
        assert await relay_tail(store, notifier, clock, 0) == 1
        assert len(notifier.calls) == 1
    finally:
        store.close()


async def test_tail_relay_failures_never_raise(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        _append(store, clock, "HaltSet", _halt_payload("d"), "h1")
        assert await relay_tail(store, _Notifier(fail=True), clock, 0) == 1
    finally:
        store.close()


async def test_seat_relay_failure_never_raises_out_of_the_crash_path(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        task = _task(SNIPER, _boom, clock, store, notifier=_Notifier(fail=True))
        await _crash_until_exhausted(task, store, clock, SNIPER)
        assert task.restarts == RESTART_CAPACITY
        assert len(store.read(types=["Escalation"], limit=None)) == 1
    finally:
        store.close()


def test_clock_trailing_the_head_refuses_the_append(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert CLOCK_SKEW_S == 5.0
        ahead = FixtureClock(start=BASE + 100.0)
        _append(store, ahead, "JournalNote", _note_payload("ahead"), "ahead")
        behind = FixtureClock(start=BASE)
        with pytest.raises(ClockSkew):
            append_escalation(
                store,
                behind,
                kind="heartbeat_stale",
                seat=SNIPER,
                detail="d",
                source="paper",
                correlation_id="desk",
            )
        rows = store.read(types=["Escalation"], limit=None)
        assert len(rows) == 1
        assert rows[0]["payload"]["kind"] == "clock_skew"
        assert rows[0]["payload"]["detail"] == "clock trails ledger head; appends refused"
    finally:
        store.close()
