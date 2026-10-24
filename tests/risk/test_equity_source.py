"""Equity source parity: one configured budget yields one day-start equity on every path."""

from __future__ import annotations

import random
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.supervisor.scheduler import ROSTER, Supervisor
from pumpgrok.supervisor.seat_task import SeatContext
from pumpgrok.tools._common import fold_current_state

BASE = 1_767_225_600.0  # 2026-01-01T00:00:00Z
FIVE_SOL = 5_000_000_000
HALF_LAMPORT_OVER_TEN = Decimal("10.0000000005")
TEN_SOL_ROUNDED = 10_000_000_001


def _empty_store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def _engine_day_start(store: LedgerStore, clock: FixtureClock, budget: RiskBudget) -> int:
    engine = RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(3)),
        clock=clock,
        budget=budget,
    )
    return int(engine._fold().day_start_equity_lamports)


async def _scheduler_day_start(store: LedgerStore, clock: FixtureClock, budget: RiskBudget) -> int:
    async def _ok(ctx: SeatContext) -> dict[str, Any]:
        return {"ok": True}

    supervisor = Supervisor(
        store=store,
        clock=clock,
        rng=make_rng(7),
        cycles=dict.fromkeys(ROSTER, _ok),
        budget=budget,
    )
    await supervisor.run_once()
    rows = [row for row in store.read(limit=None) if row["type"] == "DailyRollover"]
    assert len(rows) == 1
    return int(rows[0]["payload"]["day_start_equity_lamports"])


def test_helper_converts_configured_sol_to_lamports() -> None:
    assert budget_equity_lamports(RiskBudget(paper_equity_sol=Decimal("5"))) == FIVE_SOL
    assert RiskBudget(paper_equity_sol=Decimal("5")).paper_equity_lamports == FIVE_SOL


def test_helper_rounds_half_up_not_truncates() -> None:
    budget = RiskBudget(paper_equity_sol=HALF_LAMPORT_OVER_TEN)
    assert budget_equity_lamports(budget) == TEN_SOL_ROUNDED
    assert budget.paper_equity_lamports == TEN_SOL_ROUNDED


def test_default_budget_equity_is_unchanged() -> None:
    assert RiskBudget().paper_equity_lamports == 10_000_000_000


async def test_scheduler_and_engine_day_start_match_at_five_sol(tmp_path: Path) -> None:
    budget = RiskBudget(paper_equity_sol=Decimal("5"))
    clock = FixtureClock(start=BASE)
    store = _empty_store(tmp_path)
    try:
        engine_equity = _engine_day_start(store, clock, budget)
        scheduler_equity = await _scheduler_day_start(store, clock, budget)
    finally:
        store.close()
    assert engine_equity == FIVE_SOL
    assert scheduler_equity == FIVE_SOL
    assert engine_equity == scheduler_equity


async def test_scheduler_and_engine_convert_fractional_sol_identically(tmp_path: Path) -> None:
    budget = RiskBudget(paper_equity_sol=HALF_LAMPORT_OVER_TEN)
    clock = FixtureClock(start=BASE)
    store = _empty_store(tmp_path)
    try:
        engine_equity = _engine_day_start(store, clock, budget)
        scheduler_equity = await _scheduler_day_start(store, clock, budget)
    finally:
        store.close()
    assert engine_equity == TEN_SOL_ROUNDED
    assert scheduler_equity == TEN_SOL_ROUNDED


def test_read_tools_use_budget_when_meta_row_absent(tmp_path: Path) -> None:
    clock = FixtureClock(start=BASE)
    store = _empty_store(tmp_path)
    try:
        with_budget = fold_current_state(store, clock, RiskBudget(paper_equity_sol=Decimal("5")))
        without_budget = fold_current_state(store, clock)
    finally:
        store.close()
    assert with_budget.day_start_equity_lamports == FIVE_SOL
    assert without_budget.day_start_equity_lamports == 0
