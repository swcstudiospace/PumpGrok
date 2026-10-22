"""INV-R-31 (fill leg): fills price from bonding-curve reserves only, never the quote."""

from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import buy_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
SIZE = 200_000_000


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


class _ScriptedCurves:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


async def test_paper_fill_prices_from_curve_math(tmp_path: Path) -> None:
    """INV-R-31: FillRecorded price equals curve_math.buy_out for the executed size."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(51))
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, random.Random(51)),
            clock=clock,
            autonomy="autonomous-paper",
            get_reserves=lambda _mint: (S0, T0),
            env={},
        )
        fees = FeeModel()
        snap = CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=ids,
            clock=clock,
            rng=make_rng(51),
            budget=RiskBudget(),
            fees=fees,
            price_source=_ScriptedCurves([snap, snap]),
            p_drop=0.0,
        )
        order = OrderRequest(
            ticket_id=TICKET,
            mint=MINT,
            side="buy",
            decision_id=ids.ulid(),
            size_lamports=SIZE,
            max_slippage_bps=100,
            approval_id=f"apr-{ids.ulid()}",
            correlation_id="test",
        )
        task = asyncio.create_task(adapter.place(order, seat="bot-04-sniper"))
        for _ in range(400):
            if task.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        fill = await task
        x_net = SIZE - fees.venue_fee(SIZE)
        expected_units = buy_out(S0, T0, x_net)
        assert fill.filled_units == expected_units
        assert fill.price_avg == Decimal(x_net) / Decimal(expected_units)
        assert fill.route == "curve"
        assert fill.venue_tx_ref.startswith("dry_run:")
        rows = store.read(types=["FillRecorded"], limit=None)
        assert len(rows) == 1
        payload = rows[0]["payload"]
        assert payload["filled_units"] == expected_units
        assert payload["price_avg"] == str(Decimal(x_net) / Decimal(expected_units))
        assert payload["route"] == "curve"
        assert payload["curve_before_s"] == S0
        assert payload["curve_after_s"] == S0
        assert "jupiter" not in {k.lower() for k in payload}
    finally:
        store.close()
