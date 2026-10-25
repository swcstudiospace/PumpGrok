"""Regression tests for Greptile findings 14, 16, 17 and 28 (scheduler.py).

14: the DailyRollover baseline is the folded account equity at the day's start,
    written before any seat of that day runs.
16: a slow seat never holds other seats or the next serve tick, and a seat never
    overlaps itself.
17: recorded LLM latency replays under the wall clock without advancing it.
28: serve shutdown runs the final snapshot, JSONL export and stopped-health write.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.export import EXPORT_SEQ_KEY
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, WallClock, format_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.supervisor import scheduler
from pumpgrok.supervisor.lifecycle import shutdown
from pumpgrok.supervisor.scheduler import (
    ROSTER,
    DegradedState,
    Supervisor,
    serve_replay,
)
from pumpgrok.supervisor.scheduler.replay_cycles import _replay_cycles
from pumpgrok.supervisor.seat_task import SeatContext, SeatTask

REPO = Path(__file__).resolve().parents[2]
SMOKE_10M = REPO / "tests" / "fixtures" / "replay" / "smoke-10m"
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"

EQUITY = 10_000_000_000
DAY_ONE = datetime(2026, 10, 21, 10, 0, 0, tzinfo=UTC).timestamp()
DAY_TWO = datetime(2026, 10, 22, 10, 0, 0, tzinfo=UTC).timestamp()
MINT = "So11111111111111111111111111111111111111112"


def _store(tmp_path: Path, *, meta_equity: bool = True) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    if meta_equity:
        store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


def _cycles(**overrides: Any) -> dict[str, Any]:
    cycles: dict[str, Any] = dict.fromkeys(ROSTER, _ok)
    cycles.update(overrides)
    return cycles


def _fill(store: LedgerStore, clock: FixtureClock, cash_delta: int, label: str) -> None:
    """Realized cash movement, same row shape the risk tests use."""
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"fill|{label}",
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": f"ord-{label}",
            "decision_id": f"dec-{label}",
            "side": "sell",
            "mint": MINT,
            "filled_lamports": 0,
            "filled_units": 0,
            "filled_fraction": "1",
            "price_avg": "0.00001",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": cash_delta,
            "latency_s": "1.0",
            "venue_tx_ref": "",
        },
    )


def _rollover(store: LedgerStore, day: str) -> dict[str, Any]:
    rows = [
        row
        for row in store.read(types=["DailyRollover"], limit=None)
        if row["payload"]["day_utc"] == day
    ]
    assert len(rows) == 1, f"expected one DailyRollover for {day}, got {len(rows)}"
    payload = rows[0]["payload"]
    assert isinstance(payload, dict)
    return payload


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, make_rng(11)),
        clock=clock,
        autonomy="autonomous-paper",
        env={},
    )


# -- finding 14: daily rollover baseline --------------------------------------


async def test_rollover_baseline_is_account_equity_at_day_start(tmp_path: Path) -> None:
    clock = FixtureClock(start=DAY_ONE)
    store = _store(tmp_path)
    try:
        sup = Supervisor(store=store, clock=clock, rng=make_rng(7), cycles=_cycles())
        await sup.tick_once()
        assert _rollover(store, "2026-10-21")["day_start_equity_lamports"] == EQUITY
        # Day one loses 6 % of the account before the next UTC day starts.
        _fill(store, clock, -600_000_000, "day-one-loss")
        clock.advance_to(DAY_TWO)
        await sup.tick_once()
        assert _rollover(store, "2026-10-22")["day_start_equity_lamports"] == EQUITY - 600_000_000
    finally:
        store.close()


async def test_rollover_baseline_halts_only_on_new_day_loss(tmp_path: Path) -> None:
    """The 5 % halt compares against the new day's start, not the genesis equity."""
    clock = FixtureClock(start=DAY_ONE)
    store = _store(tmp_path)
    try:
        sup = Supervisor(store=store, clock=clock, rng=make_rng(7), cycles=_cycles())
        await sup.tick_once()
        _fill(store, clock, -600_000_000, "day-one-loss")
        clock.advance_to(DAY_TWO)
        await sup.tick_once()
        # No further loss on day two: yesterday's 6 % drop must not trip today.
        assert _engine(store, clock).evaluate_halts() is None
        assert store.read(types=["HaltSet"], limit=None) == []
    finally:
        store.close()


async def test_rollover_baseline_without_metadata_is_not_zero(tmp_path: Path) -> None:
    clock = FixtureClock(start=DAY_ONE)
    store = _store(tmp_path, meta_equity=False)
    try:
        sup = Supervisor(store=store, clock=clock, rng=make_rng(7), cycles=_cycles())
        await sup.tick_once()
        expected = RiskBudget().paper_equity_lamports
        assert _rollover(store, "2026-10-21")["day_start_equity_lamports"] == expected
    finally:
        store.close()


async def test_rollover_precedes_first_seat_of_the_day(tmp_path: Path) -> None:
    """A seat that moves equity on the day's first tick must not shift the baseline."""
    clock = FixtureClock(start=DAY_ONE)
    store = _store(tmp_path)
    try:

        async def _trader(ctx: SeatContext) -> dict[str, Any]:
            _fill(store, clock, -600_000_000, "first-tick-loss")
            return {}

        sup = Supervisor(
            store=store,
            clock=clock,
            rng=make_rng(7),
            cycles=_cycles(**{"bot-06-exit": _trader}),
        )
        await sup.tick_once()
        assert _rollover(store, "2026-10-21")["day_start_equity_lamports"] == EQUITY
    finally:
        store.close()


# -- finding 16: slow seats do not block other seats or the next tick ----------


async def _settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


async def test_slow_chief_does_not_hold_other_seats_or_next_tick(tmp_path: Path) -> None:
    clock = FixtureClock(start=1_000.0)
    store = _store(tmp_path)
    release = asyncio.Event()
    chief_calls = 0

    async def _slow_chief(ctx: SeatContext) -> dict[str, Any]:
        nonlocal chief_calls
        chief_calls += 1
        await release.wait()
        return {}

    sup = Supervisor(
        store=store,
        clock=clock,
        rng=make_rng(11),
        cycles=_cycles(**{"bot-00-chief": _slow_chief}),
    )
    serving = asyncio.ensure_future(sup.serve_forever())
    try:
        await _settle()
        # Seventy virtual seconds: chief (cadence 60 s) is still running at t=60.
        for _ in range(70):
            clock.advance_to(clock.now() + 1.0)
            await _settle()
        assert sup.tasks["bot-00-chief"].cycles == 0
        assert sup.tasks["bot-01-scout"].cycles >= 6  # cadence 10 s
        assert sup.tasks["bot-08-signal"].cycles >= 50  # cadence 1 s
        # Due again at t=60 while still running: must not start a second run.
        assert chief_calls == 1
        release.set()
        await _settle()
        assert sup.tasks["bot-00-chief"].cycles == 1
        sup.request_stop("test")
        clock.advance_to(clock.now() + 1.0)
        assert await asyncio.wait_for(serving, timeout=5) == 0
    finally:
        release.set()
        if not serving.done():
            serving.cancel()
        store.close()


# -- finding 17: recorded latency under the wall clock --------------------------


async def test_recorded_llm_latency_replays_under_wall_clock(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        dataset = load_dataset(SMOKE_10M)
        llm = load_llm_records(SMOKE_10M)
        assert llm is not None
        cycles = _replay_cycles(
            clock=WallClock(),
            rng=make_rng(11),
            store=store,
            risk=None,
            degraded=DegradedState(),
            dataset_events=list(dataset.events),
            replay_llm=llm,
            dataset_name=dataset.manifest.dataset,
            filter_cfg=FilterSettings(),
        )
        task = SeatTask(
            "bot-08-signal",
            1.0,
            cycles["bot-08-signal"],
            clock=WallClock(),
            rng=make_rng(11),
            store=store,
        )
        ctx = SeatContext(seat_id="bot-08-signal", clock=WallClock(), rng=make_rng(11), store=store)
        assert await task.run_guarded(ctx) == "ok"
        assert task.crashes == 0
    finally:
        store.close()


# -- finding 28: stop runs the final exports -----------------------------------


async def test_stop_writes_snapshot_export_and_stopped_health(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[Any] = []
    installed = asyncio.Event()

    def _capture_stop(stop: Any) -> None:
        captured.append(stop)
        installed.set()

    monkeypatch.setattr(scheduler.serve, "install_signal_handlers", _capture_stop)
    ledger = tmp_path / "var" / "ledger.sqlite"
    health = tmp_path / "health.json"

    async def _stop_when_serving() -> None:
        await installed.wait()
        captured[0]("SIGTERM")

    stopper = asyncio.ensure_future(_stop_when_serving())
    code = await serve_replay(
        SMOKE,
        FilterSettings(),
        seed=20260101,
        port=0,
        ledger_path=ledger,
        health_path=health,
    )
    await stopper
    assert code == 0

    assert json.loads(health.read_text(encoding="utf-8"))["status"] == "stopped"
    store = LedgerStore(str(ledger))
    try:
        snapshot = store.latest_snapshot()
        assert snapshot is not None
        assert snapshot["state"]["meta"]["status"] == "stopped"
        assert store.get_meta(EXPORT_SEQ_KEY) is not None
    finally:
        store.close()


# -- round 3 finding 4: shutdown drains only the supervisor's own seat tasks ----


async def test_shutdown_never_cancels_a_caller_outside_the_supervisor(tmp_path: Path) -> None:
    """A task awaiting the service (for example serve_replay) must survive shutdown."""
    store = _store(tmp_path)
    try:
        supervisor = Supervisor(store=store, clock=WallClock(), rng=make_rng(7), cycles=_cycles())

        async def _caller() -> str:
            await asyncio.sleep(0.3)
            return "returned"

        caller = asyncio.ensure_future(_caller())
        await asyncio.sleep(0)
        code = await shutdown(
            supervisor,
            store=store,
            health_path=str(tmp_path / "health.json"),
            journal_dir=str(tmp_path / "journal"),
            trades_path=str(tmp_path / "trades.jsonl"),
            grace_s=0.05,
        )
        assert code == 0
        assert await caller == "returned"
    finally:
        store.close()
