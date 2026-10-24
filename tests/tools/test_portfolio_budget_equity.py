"""Finding D: portfolio tools fold equity from the configured budget, as risk.drawdown does.

With no ``initial_equity_lamports`` meta row, exposure and pnl must report the configured
equity rather than zero, so they agree with risk.drawdown.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.risk_budget import RiskBudget, budget_equity_lamports
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.portfolio.exposure import ExposureIn, build_exposure_tool
from pumpgrok.tools.portfolio.pnl import PnlIn, build_pnl_tool
from pumpgrok.tools.risk.drawdown import DrawdownIn, build_drawdown_tool

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
FIVE_SOL_LAMPORTS = 5_000_000_000


async def test_exposure_and_pnl_report_the_budget_equity_that_drawdown_reports(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    budget = RiskBudget(paper_equity_sol=Decimal("5"))
    try:
        assert store.get_meta("initial_equity_lamports") is None
        exposure = await build_exposure_tool(store, clock, budget=budget)(ExposureIn())
        pnl = await build_pnl_tool(store, clock, budget=budget)(PnlIn(window="all"))
        drawdown = await build_drawdown_tool(store, budget, clock)(DrawdownIn())
    finally:
        store.close()

    assert budget_equity_lamports(budget) == FIVE_SOL_LAMPORTS
    assert exposure.equity_lamports == FIVE_SOL_LAMPORTS
    assert pnl.day_start_equity_lamports == FIVE_SOL_LAMPORTS
    assert pnl.peak_equity_lamports == FIVE_SOL_LAMPORTS
    assert drawdown.current_equity_lamports == FIVE_SOL_LAMPORTS
    assert exposure.equity_lamports == drawdown.current_equity_lamports
    assert pnl.peak_equity_lamports == drawdown.peak_equity_lamports
