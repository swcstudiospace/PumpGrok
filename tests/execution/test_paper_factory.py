"""Production composition refuses injected curve sources; the factory is the only entry.

Until the replay-bound factory lands, these tests drive the existing ``build_adapter``
entry point, which is the production construction site they must eventually cover.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_adapter
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-101"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


class ScriptedCurves:
    """Injected test source: pops one scripted snapshot per read, holds the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _factory_adapter(
    tmp_path: Path, reads: list[CurveSnapshot]
) -> tuple[PaperAdapter, FixtureClock, LedgerStore]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    risk = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = build_adapter(
        object(),
        store=store,
        risk=risk,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        price_source=ScriptedCurves(reads),
        p_drop=0.0,
    )
    return adapter, clock, store


async def _place(adapter: PaperAdapter, clock: FixtureClock, request: OrderRequest) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def test_factory_injected_fixture_buy_is_not_filled(tmp_path: Path) -> None:
    """RED: a fixture source injected through the factory fills a BUY that must be refused."""
    adapter, clock, store = _factory_adapter(tmp_path, [_snap("fixture")] * 3)
    request = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        token_units=None,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError:
        pass
    kinds = [event["type"] for event in store.read(limit=None)]
    assert "FillRecorded" not in kinds
