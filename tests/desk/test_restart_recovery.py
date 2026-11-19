"""RT-04 / criterion 11: a desk crashes mid-run and rebuilds from a fresh store.

The desk writes positions under two strategies and under a legacy ticket, marks one position up,
and crashes in the middle of an exit pass. A fresh store on the same file then rebuilds the desk
state. Probation, the desk-wide watch set and the exit peaks come back from the ledger. Tapes
start empty, so a strategy with an empty tape makes no decision until its window refills. The
rebuild appends no ledger row. Nothing here is skipped: the clock is a FixtureClock, the curve
is a fixed double, and the crash is a BaseException that no desk code swallows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok.config.settings import ExitsSettings
from pumpgrok.engine.models import PRICE_SCALE
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.ledger.ticket_refs import append_with_ticket_ref
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.strategies.base import Intent, StrategyContext, TickSnapshot
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.supervisor.exit_rules import ExitRules
from pumpgrok.supervisor.recovery import rebuild_desk_state

START = 1_700_000_000.0
MOM_MINT = "MintMomentum1111111111111111111111111111111"
REV_MINT = "MintReversion11111111111111111111111111111"
MANUAL_MINT = "MintManual111111111111111111111111111111"
CLOSED_MINT = "MintClosed111111111111111111111111111111"
CFG = ExitsSettings(
    stop_loss_pct=30.0,
    take_profit_pct=120.0,
    trailing_stop_pct=35.0,
    max_hold_seconds=3600.0,
    stop_loss_poll_seconds=15.0,
)


class SimulatedCrash(BaseException):
    """The desk dies mid-run. A BaseException, so no ``except Exception`` in the desk catches it."""


class _Curves:
    """Every mint reads a 100 price, equal to its entry. The read for MANUAL_MINT crashes."""

    async def curve(self, mint: str) -> CurveSnapshot:
        if mint == MANUAL_MINT:
            raise SimulatedCrash(mint)
        return CurveSnapshot(mint=mint, s_lamports=100, t_units=1, complete=False, source="rpc")

    def last_open_reserves(self, mint: str) -> None:
        return None


class _Sells:
    """Records every sell. No sell is expected before the crash: every price holds at entry."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, mint: str, ticket: str, units: int, rule: str) -> dict[str, object]:
        self.calls.append(mint)
        return {"status": "filled", "reason": ""}


def _create(path: Path) -> LedgerStore:
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", "1000000")
    store.set_meta("source", "paper")
    return store


def _row(clock: FixtureClock, key: str, event_type: str, payload: dict[str, object]) -> dict:
    return {
        "ts_utc": format_ts_utc(clock.now()),
        "source": "paper",
        "correlation_id": "test",
        "idempotency_key": key,
        "type": event_type,
        "payload": payload,
    }


def _open(
    store: LedgerStore, clock: FixtureClock, mint: str, ticket: str, strategy: str | None
) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_entry": "100",
        "token_units": 10,
        "cost_basis_lamports": 1000,
        "opened_ts_utc": format_ts_utc(clock.now()),
        "ticket_id": ticket,
    }
    row = _row(clock, f"open|{ticket}", "PositionOpened", payload)
    if strategy is None:
        store.append_batch([row])
    else:
        append_with_ticket_ref(store, row, ticket_id=ticket, strategy_id=strategy)


def _mark(store: LedgerStore, clock: FixtureClock, mint: str, spot: str) -> None:
    prices = {mint: {"spot": spot, "mtm_lamports": 1500, "venue_fee_lamports": 0}}
    payload = {
        "source": "paper",
        "ts_source": "curve",
        "cash_lamports": 0,
        "equity_lamports": 0,
        "unrealized_lamports": 0,
        "prices_json": json.dumps(prices),
    }
    store.append_batch([_row(clock, f"mtm|{mint}|{spot}", "MarkToMarket", payload)])


def _close(store: LedgerStore, clock: FixtureClock, mint: str) -> None:
    payload = {
        "source": "paper",
        "mint": mint,
        "price_exit": "50",
        "proceeds_lamports": 500,
        "realized_pnl_lamports": -500,
        "reason": "stop_loss",
    }
    store.append_batch([_row(clock, f"close|{mint}", "PositionClosed", payload)])


def _tick(strategy: MomentumBreakout, ts: float, price: int) -> tuple[Intent, ...]:
    tick = TickSnapshot(
        mint=MOM_MINT,
        ts=ts,
        launch_ts=START,
        price_lamports=price,
        unique_buyers=5,
        curve_progress=0.1,
    )
    return strategy.on_tick(StrategyContext(now=ts, version_id="test", tick=tick, tape=()))


async def test_crash_mid_run_rebuilds_probation_watch_set_and_peaks_from_a_fresh_store(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ledger.sqlite"
    clock = FixtureClock(START)
    store = _create(path)
    sells = _Sells()
    try:
        _open(store, clock, MOM_MINT, "mom-1", "momentum_breakout")
        _mark(store, clock, MOM_MINT, "150")
        _open(store, clock, REV_MINT, "rev-1", "mean_reversion")
        _open(store, clock, CLOSED_MINT, "mom-2", "momentum_breakout")
        _close(store, clock, CLOSED_MINT)
        _open(store, clock, MANUAL_MINT, "manual-1", None)
        rules = ExitRules(
            store=store,
            curves=_Curves(),  # type: ignore[arg-type]
            exits=CFG,
            clock=clock,
            place_sell=sells,
        )
        # The pass reads MOM_MINT and REV_MINT, then crashes on MANUAL_MINT.
        with pytest.raises(SimulatedCrash):
            await rules.check(clock.now())
    finally:
        store.close()
    assert sells.calls == []

    fresh = LedgerStore(str(path))
    try:
        rows_before = fresh.count()
        momentum = MomentumBreakout()
        mean_reversion = MeanReversion()
        state = rebuild_desk_state(fresh, [momentum, mean_reversion], CFG)
        assert fresh.count() == rows_before
    finally:
        fresh.close()

    # Probation: each strategy's entries, closed mints included, from its own tickets only.
    assert state.probation == {
        "momentum_breakout": {MOM_MINT: 1, CLOSED_MINT: 1},
        "mean_reversion": {REV_MINT: 1},
    }
    assert momentum.book.probation == {MOM_MINT: 1, CLOSED_MINT: 1}
    assert mean_reversion.book.probation == {REV_MINT: 1}

    # Desk-wide watch set: every open position, across both strategies and the legacy ticket.
    assert state.watch_set == frozenset({MOM_MINT, REV_MINT, MANUAL_MINT})

    # Exit peaks: the marked position keeps its ledger peak; the others restart at entry.
    assert state.exit_peaks == {
        MOM_MINT: 150 * PRICE_SCALE,
        REV_MINT: 100 * PRICE_SCALE,
        MANUAL_MINT: 100 * PRICE_SCALE,
    }

    # Tapes and curve-based state are not restored: the rebuilt books start empty.
    assert momentum.book.tape.points(MOM_MINT) == ()
    assert mean_reversion.book.tape.points(REV_MINT) == ()
    assert momentum.book.positions == {}
    assert momentum.book.peaks == {}


async def test_cold_restart_strategy_makes_no_decision_until_its_window_refills() -> None:
    warmed = MomentumBreakout()
    cold = MomentumBreakout()
    assert _tick(warmed, START, 1_000) == ()
    # The same 1500 tick decides when the tape holds the 1000 print: threshold 1200.
    assert [intent.side for intent in _tick(warmed, START + 10, 1_500)] == ["buy"]
    # The cold strategy's tape is empty at that tick, so it makes no decision.
    assert _tick(cold, START + 10, 1_500) == ()
    # The 1500 print ages out of the 300 s lookback, then the window refills from 1000 prints.
    assert _tick(cold, START + 400, 1_000) == ()
    assert _tick(cold, START + 410, 1_000) == ()
    assert [intent.side for intent in _tick(cold, START + 420, 1_500)] == ["buy"]
