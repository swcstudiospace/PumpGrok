"""A BUY or SELL stamps the curve tick that priced it, not its confirmation instant.

The fill is priced at the CONFIRMING reserves, which were observed at the tick
``curve.ts``. A later observed tick, still before the confirmation instant, is a
valid price. Stamping the confirmation clock refuses that tick as data_stale.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
BUY_TICKET = "SOL-20260201-001"
SELL_TICKET = "SOL-20260201-002"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


class SettableCurve:
    """Serve the snapshot currently set, so a test can move the observed tick."""

    def __init__(self, snapshot: CurveSnapshot) -> None:
        self.snapshot = snapshot

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return self.snapshot


def _tick(ts: float) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source="fixture", ts=ts)


def _adapter(tmp_path: Path, clock: FixtureClock, curve: SettableCurve) -> PaperAdapter:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=curve,
        p_drop=0.0,
    )


def _request(
    adapter: PaperAdapter,
    *,
    side: Side,
    ticket: str,
    size: int | None = None,
    units: int | None = None,
) -> OrderRequest:
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT,
        side=side,
        decision_id=adapter._ids.ulid(),
        size_lamports=size,
        token_units=units,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )


async def _place(
    adapter: PaperAdapter,
    clock: FixtureClock,
    request: OrderRequest,
    *,
    seat: str,
) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat=seat, correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def _later_tick_is_admitted(
    adapter: PaperAdapter, clock: FixtureClock, priced_ts: float
) -> None:
    """A tick after the priced tick and before the confirmation instant prices a mark."""
    confirmed_at = clock.now()
    assert confirmed_at > priced_ts
    later = priced_ts + (confirmed_at - priced_ts) / 2
    row = await adapter.mark_open_positions(
        snapshots={MINT: _tick(later)}, correlation_id="test"
    )
    assert row is not None
    assert row["type"] == "MarkToMarket"


async def test_buy_stamps_the_priced_tick_not_the_confirmation_instant(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    curve = SettableCurve(_tick(START))
    adapter = _adapter(tmp_path, clock, curve)
    buy = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.BUY, ticket=BUY_TICKET, size=SIZE),
        seat="bot-04-sniper",
    )
    assert buy.filled_lamports > 0
    await _later_tick_is_admitted(adapter, clock, priced_ts=START)


async def test_sell_stamps_the_priced_tick_not_the_confirmation_instant(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    curve = SettableCurve(_tick(START))
    adapter = _adapter(tmp_path, clock, curve)
    buy = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.BUY, ticket=BUY_TICKET, size=SIZE),
        seat="bot-04-sniper",
    )
    sell_ts = clock.now()
    curve.snapshot = _tick(sell_ts)
    # The risk gate admits a SELL only on a MarkToMarket younger than mtm_interval_s.
    assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
    sell = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.SELL, ticket=SELL_TICKET, units=buy.filled_units // 2),
        seat="bot-06-exit",
    )
    assert sell.filled_units > 0
    await _later_tick_is_admitted(adapter, clock, priced_ts=sell_ts)
