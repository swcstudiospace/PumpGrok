"""Tracer: one seat schedules, heartbeats, times out honestly, health reflects.

One seat task runs under the roster scheduler within a 1 s tick, the
wrapper records heartbeats, a cycle exceeding max(30 s, 4 x cadence) via
the fixture clock counts as a crash, and health degrades while a seat is
stale (``/healthz`` 503) and recovers after (200). No wall-clock sleeps
anywhere in the supervised path.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.supervisor.health import build_status, is_ok, write_health_json
from pumpgrok.supervisor.scheduler import ROSTER, SEAT_CADENCES, Supervisor, cycle_timeout_s
from pumpgrok.supervisor.seat_task import SeatContext, SeatTask


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    return LedgerStore(str(path))


def _ctx(store: LedgerStore, clock: FixtureClock, seat: str = "bot-01-scout") -> SeatContext:
    return SeatContext(
        seat_id=seat,
        clock=clock,
        rng=make_rng(7),
        store=store,
        source="replay",
        correlation_id="desk",
    )


async def _ok_cycle(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


def test_cycle_timeout_is_max_30s_or_4x_cadence() -> None:
    assert cycle_timeout_s(5.0) == 30.0
    assert cycle_timeout_s(60.0) == 240.0
    assert cycle_timeout_s(1.0) == 30.0


async def test_one_seat_schedules_heartbeats_and_health_reflects(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    try:
        task = SeatTask("bot-01-scout", 10.0, _ok_cycle, clock=clock, rng=make_rng(7), store=store)
        assert task.is_due(clock.now())
        outcome = await task.run_guarded(_ctx(store, clock))
        assert outcome == "ok"
        assert task.cycles == 1
        assert task.crashes == 0
        assert task.last_ok is True
        assert task.last_started_at == 1_000.0
        assert task.last_finished_at == 1_000.0
        assert task.last_duration_s == 0.0
        assert not task.is_due(clock.now())
        clock.advance_to(1_010.0)
        assert task.is_due(clock.now())
    finally:
        store.close()


async def test_roster_order_starts_due_seats_in_order(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    started: list[str] = []

    async def _record(ctx: SeatContext) -> dict[str, Any]:
        started.append(ctx.seat_id)
        return {"ok": True}

    try:
        cycles = dict.fromkeys(ROSTER, _record)
        supervisor = Supervisor(store=store, clock=clock, rng=make_rng(7), cycles=cycles)
        outcomes = await supervisor.run_once()
        assert started == list(ROSTER)
        assert set(outcomes) == set(ROSTER)
        assert all(outcome == "ok" for outcome in outcomes.values())
    finally:
        store.close()


async def test_cycle_exceeding_timeout_counts_as_crash(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)

    async def _hang(ctx: SeatContext) -> dict[str, Any]:
        await ctx.clock.sleep(10_000.0)
        return {"ok": True}

    async def _pump() -> None:
        await asyncio.sleep(0)
        clock.advance_to(10_000.0)

    try:
        task = SeatTask("bot-02-risk", 5.0, _hang, clock=clock, rng=make_rng(7), store=store)
        assert task.timeout_s == 30.0
        outcome, _ = await asyncio.gather(
            task.run_guarded(_ctx(store, clock, "bot-02-risk")), _pump()
        )
        assert outcome == "crash"
        assert task.crashes == 1
        assert task.restarts == 1
        # Backoff gates rescheduling instead of sleeping: the seat is not
        # due until now + min(16, 2**0) + jitter.
        assert task.not_before is not None
        assert task.not_before > clock.now()
        assert not task.is_due(clock.now())
        clock.advance_to(task.not_before + 5.0)
        assert task.is_due(clock.now())
    finally:
        store.close()


async def test_stale_seat_degrades_health_until_recovery(tmp_path: Path) -> None:
    clock = FixtureClock(start=0.0)
    store = _store(tmp_path)
    try:
        task = SeatTask("bot-01-scout", 10.0, _ok_cycle, clock=clock, rng=make_rng(7), store=store)
        await task.run_guarded(_ctx(store, clock))
        assert not task.is_stale(clock.now())
        clock.advance_to(31.0)
        assert task.is_stale(clock.now())
        raised = await task.check_stale(clock.now())
        assert raised is True
        # Edge-triggered: one Escalation row, no repeat.
        assert store.count() == 1
        assert await task.check_stale(clock.now()) is False
        assert store.count() == 1
        status = build_status(
            mode="paper",
            autonomy_level="manual-ticket",
            ledger_status="CONSISTENT",
            ledger_source="replay",
            kill_switch=False,
            seats={"bot-01-scout": {"stale": True}},
            uptime_s=31.0,
        )
        assert not is_ok(status)
        assert status["status"] == "degraded"
        assert status["stalled"] is True
        clock.advance_to(41.0)
        await task.run_guarded(_ctx(store, clock))
        assert not task.is_stale(clock.now())
        recovered = build_status(
            mode="paper",
            autonomy_level="manual-ticket",
            ledger_status="CONSISTENT",
            ledger_source="replay",
            kill_switch=False,
            seats={"bot-01-scout": {"stale": False}},
            uptime_s=41.0,
        )
        assert is_ok(recovered)
    finally:
        store.close()


async def test_health_json_rewrites_atomically(tmp_path: Path) -> None:
    target = tmp_path / "health.json"
    first = build_status(
        mode="paper",
        autonomy_level="manual-ticket",
        ledger_status="CONSISTENT",
        ledger_source="replay",
        kill_switch=False,
        seats={},
        uptime_s=0.0,
    )
    write_health_json(str(target), first)
    assert target.is_file()
    second = build_status(
        mode="paper",
        autonomy_level="autonomous-paper",
        ledger_status="CONSISTENT",
        ledger_source="replay",
        kill_switch=False,
        seats={},
        uptime_s=10.0,
    )
    write_health_json(str(target), second)

    assert json.loads(target.read_text(encoding="utf-8"))["autonomy_level"] == "autonomous-paper"
    assert SEAT_CADENCES["bot-02-risk"] == 5.0
