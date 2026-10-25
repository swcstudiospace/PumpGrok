"""INV-R-15..18: bounded restart, observe-only consequences, shutdown, health.

Owning tests for SAFETY_INVARIANTS.md section 3.3 rows INV-R-15 (bounded
restart with 1,2,4,8,16 s backoff plus jitter on FixtureClock, then
observe-only with one escalation and an unchanged hash chain), INV-R-16
(observe-only consequences per seat), INV-R-17 (SIGTERM drain, snapshot,
flush, stopped health, exit 0, no force on a second signal) and INV-R-18
(health truthfulness with atomic var/health.json).

Harness: SeatTask/Supervisor driven by FixtureClock and make_rng(11); no
wall clock, no network. Companion file tests/supervisor/test_restarts.py
covers the same machinery under different names; these are the matrix
owners with the exact section 3.3 assertions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.logging.json import bind_seat
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.supervisor.health import is_ok, write_health_json
from pumpgrok.supervisor.lifecycle import shutdown
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import ObserveOnly, SeatContext, SeatTask

BASE = 1_000_000.0
MINT = "B" * 44


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    # Fail-closed contract (INT-02): shutdown and the exit halt record this equity.
    store.set_meta("initial_equity_lamports", "10000000000")
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


async def _boom(ctx: SeatContext) -> dict[str, Any]:
    raise RuntimeError("seat crashed")


async def _ok(ctx: SeatContext) -> dict[str, Any]:
    return {"ok": True}


async def test_bounded_restart_then_observe_only(tmp_path: Path) -> None:
    """INV-R-15: 1,2,4,8,16 s + jitter backoff, then latch with one escalation."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        pre_crash = [(row["seq"], row["hash"]) for row in store.read(limit=None)]
        latch = ObserveOnly()
        task = SeatTask(
            "bot-04-sniper",
            1.0,
            _boom,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=latch,
        )
        healthy = SeatTask(
            "bot-00-chief",
            1.0,
            _ok,
            clock=clock,
            rng=make_rng(11),
            store=store,
            observe_only=latch,
        )
        expect_rng = make_rng(11)
        for attempt in range(5):
            now = clock.now()
            assert await task.run_guarded(_ctx(store, clock, "bot-04-sniper")) == "crash"
            assert await healthy.run_guarded(_ctx(store, clock, "bot-00-chief")) == "ok"
            base = min(16.0, 2.0**attempt)
            expected_wait = base + expect_rng.uniform(0.0, 1.0)
            assert task.not_before is not None
            assert task.not_before == now + expected_wait
            clock.advance_to(task.not_before + 60.0)
        assert task.restarts == 5
        assert not latch.is_latched("bot-04-sniper")
        # Sixth crash inside the rolling hour: no restart, latch + one escalation.
        assert await task.run_guarded(_ctx(store, clock, "bot-04-sniper")) == "crash"
        assert await healthy.run_guarded(_ctx(store, clock, "bot-00-chief")) == "ok"
        assert task.restarts == 5
        assert latch.is_latched("bot-04-sniper")
        assert latch.reason("bot-04-sniper") == "bot_restart_exhausted"
        assert healthy.cycles == 6
        escalations = store.read(types=["Escalation"], limit=None)
        assert len(escalations) == 1
        payload = escalations[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["kind"] == "bot_restart_exhausted"
        assert payload["seat"] == "bot-04-sniper"
        # The crash never rewrote history: pre-crash rows keep their hashes.
        post_crash = [(row["seq"], row["hash"]) for row in store.read(limit=None)]
        assert post_crash[: len(pre_crash)] == pre_crash
        assert store.verify() is True
    finally:
        store.close()


async def test_observe_only_sniper_blocks_buys(tmp_path: Path) -> None:
    """INV-R-16: latched sniper stops buys desk-wide through the synced engine."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, make_rng(11)),
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (42_000_000_000, 764_000_000_000_000),
            env={},
        )
        cycles = dict.fromkeys(ROSTER, _ok)
        cycles["bot-04-sniper"] = _boom
        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(11), cycles=cycles, risk=engine
        )
        for _ in range(6):
            outcomes = await supervisor.run_once()
            assert outcomes["bot-04-sniper"] == "crash"
            assert outcomes["bot-00-chief"] == "ok"
            clock.advance_to(clock.now() + 60.0)
        assert supervisor.observe_only.is_latched("bot-04-sniper")
        assert not supervisor.observe_only.is_latched("bot-00-chief")
        assert supervisor.tasks["bot-00-chief"].cycles == 6
        kinds = [event["payload"]["kind"] for event in store.read(types=["Escalation"], limit=None)]
        assert kinds == ["bot_restart_exhausted"]
        # The end-of-tick sync pushed the latch into the engine: buys refuse.
        factory = IdFactory(clock, make_rng(11))
        with bind_seat("bot-04-sniper"):
            buy = OrderRequest(
                ticket_id="SOL-20260101-001",
                mint=MINT,
                side=Side.BUY,
                decision_id=factory.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id="desk",
            )
            refused = engine.check(buy, seat="bot-04-sniper", source="paper")
        assert refused.passed is False
        assert refused.reason == "seat_may_trade"
    finally:
        store.close()


async def test_observe_only_exit_sets_halt(tmp_path: Path) -> None:
    """INV-R-16: latched exit appends HaltSet(reason=manual)."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        cycles = dict.fromkeys(ROSTER, _ok)
        cycles["bot-06-exit"] = _boom
        supervisor = Supervisor(store=store, clock=clock, rng=make_rng(11), cycles=cycles)
        for _ in range(6):
            await supervisor.run_once()
            clock.advance_to(clock.now() + 60.0)
        assert supervisor.observe_only.is_latched("bot-06-exit")
        halts = store.read(types=["HaltSet"], limit=None)
        assert len(halts) == 1
        payload = halts[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["reason"] == "manual"
        assert payload["detail"] == "exit seat observe-only"
    finally:
        store.close()


async def test_observe_only_risk_blocks_buys_exits_continue(tmp_path: Path) -> None:
    """INV-R-16: latched risk refuses buys desk-wide while a stop-loss sells."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, make_rng(11)),
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (42_000_000_000, 764_000_000_000_000),
            env={},
        )
        cycles = dict.fromkeys(ROSTER, _ok)
        cycles["bot-02-risk"] = _boom
        supervisor = Supervisor(
            store=store, clock=clock, rng=make_rng(11), cycles=cycles, risk=engine
        )
        for _ in range(6):
            await supervisor.run_once()
            clock.advance_to(clock.now() + 60.0)
        assert supervisor.observe_only.is_latched("bot-02-risk")
        factory = IdFactory(clock, make_rng(11))
        with bind_seat("bot-04-sniper"):
            buy = OrderRequest(
                ticket_id="SOL-20260101-002",
                mint=MINT,
                side=Side.BUY,
                decision_id=factory.ulid(),
                size_lamports=10_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id="desk",
            )
            refused = engine.check(buy, seat="bot-04-sniper", source="paper")
        assert refused.reason == "seat_may_trade"
        with bind_seat("bot-06-exit"):
            sell = OrderRequest(
                ticket_id="SOL-20260101-002",
                mint=MINT,
                side=Side.SELL,
                decision_id=factory.ulid(),
                token_units=1_000_000,
                max_slippage_bps=100,
                approval_id=f"apr-{factory.ulid()}",
                correlation_id="desk",
            )
            exit_decision = engine.check(
                sell, seat="bot-06-exit", exit_reason="stop_loss", source="paper"
            )
        assert exit_decision.reason != "seat_may_trade"
    finally:
        store.close()


async def test_sigterm_drains_and_snapshots(tmp_path: Path) -> None:
    """INV-R-17: stop, drain, snapshot, export, stopped health, exit 0; no force."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        cycles = dict.fromkeys(ROSTER, _ok)
        supervisor = Supervisor(store=store, clock=clock, rng=make_rng(11), cycles=cycles)
        await supervisor.run_once()
        head_before = store.count()
        assert head_before >= 1  # at least the DailyRollover row
        supervisor.request_stop("SIGTERM")
        # A second signal never forces: the stop stays recorded, nothing raises.
        supervisor.request_stop("SIGTERM")
        assert supervisor.stopped is True
        health_path = tmp_path / "var" / "health.json"
        journal_dir = tmp_path / "var" / "journal"
        trades_path = tmp_path / "var" / "trades.jsonl"
        rc = await shutdown(
            supervisor,
            store=store,
            health_path=str(health_path),
            journal_dir=str(journal_dir),
            trades_path=str(trades_path),
        )
        assert rc == 0
        snapshot = store.latest_snapshot()
        assert snapshot is not None
        assert snapshot["seq"] == store.count()
        assert snapshot["seq"] == head_before
        status = json.loads(health_path.read_text(encoding="utf-8"))
        assert status["status"] == "stopped"
        journal_lines = [
            line
            for path in sorted(journal_dir.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert len(journal_lines) == store.count()
    finally:
        store.close()


async def test_healthz_reflects_staleness(tmp_path: Path) -> None:
    """INV-R-18: 503 while a seat is stale, 200 on recovery; file equals body."""
    clock = FixtureClock(start=BASE)
    store = _store(tmp_path)
    try:
        cycles = dict.fromkeys(ROSTER, _ok)
        supervisor = Supervisor(store=store, clock=clock, rng=make_rng(11), cycles=cycles)
        await supervisor.run_once()
        fresh = supervisor.health_status()
        assert fresh["status"] == "ok"
        assert is_ok(fresh) is True
        health_path = tmp_path / "var" / "health.json"
        write_health_json(str(health_path), fresh)
        assert json.loads(health_path.read_text(encoding="utf-8")) == fresh
        # No fresh cycle for over three cadences of the slowest seat: stale.
        clock.advance_to(BASE + 3600.0)
        stale = supervisor.health_status()
        assert stale["stalled"] is True
        assert stale["status"] == "degraded"
        assert is_ok(stale) is False
        write_health_json(str(health_path), stale)
        assert json.loads(health_path.read_text(encoding="utf-8")) == stale
        # Recovery: one more cycle clears staleness and returns 200.
        await supervisor.run_once()
        recovered = supervisor.health_status()
        assert recovered["status"] == "ok"
        assert is_ok(recovered) is True
        write_health_json(str(health_path), recovered)
        assert json.loads(health_path.read_text(encoding="utf-8")) == recovered
    finally:
        store.close()
