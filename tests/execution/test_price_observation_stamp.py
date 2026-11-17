"""A BUY or SELL stamps the curve tick that priced it, not its confirmation instant.

The fill is priced at the CONFIRMING reserves, which were observed at the tick
``curve.ts``. Verified replay reads the latest tick at or before the virtual clock,
so the priced tick is re-read after confirmation: that tick is still a valid price
only when the stamp is the priced tick. Stamping the confirmation clock refuses it
as stale.
"""

from __future__ import annotations

import asyncio
import random
from pathlib import Path

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.paper_adapter import PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

from .replay_support import replay_authority, tick

START = 1_769_900_000.0
EQUITY = 10_000_000_000
BUY_TICKET = "SOL-20260201-001"
SELL_TICKET = "SOL-20260201-002"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


def _adapter(tmp_path: Path, clock: FixtureClock) -> PaperAdapter:
    """Replay-bound adapter over one verified tick of S0/T0 at START."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "replay")
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    replay = replay_authority(tmp_path, clock, [tick(START, MINT, S0, T0)])
    return build_paper_adapter(
        object(),
        store=store,
        risk=engine,
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        replay=replay,
        source="replay",
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


async def _priced_tick_is_admitted(
    adapter: PaperAdapter, clock: FixtureClock, priced_ts: float
) -> None:
    """After confirmation, re-reading the priced tick prices a mark: the stamp is that tick."""
    assert clock.now() > priced_ts
    row = await adapter.mark_open_positions(correlation_id="test")
    assert row is not None
    assert row["type"] == "MarkToMarket"


async def test_buy_stamps_the_priced_tick_not_the_confirmation_instant(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    adapter = _adapter(tmp_path, clock)
    buy = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.BUY, ticket=BUY_TICKET, size=SIZE),
        seat="bot-04-sniper",
    )
    assert buy.filled_lamports > 0
    await _priced_tick_is_admitted(adapter, clock, priced_ts=START)


async def test_sell_stamps_the_priced_tick_not_the_confirmation_instant(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    adapter = _adapter(tmp_path, clock)
    buy = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.BUY, ticket=BUY_TICKET, size=SIZE),
        seat="bot-04-sniper",
    )
    # The risk gate admits a SELL only on a MarkToMarket younger than mtm_interval_s.
    assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
    sell = await _place(
        adapter,
        clock,
        _request(adapter, side=Side.SELL, ticket=SELL_TICKET, units=buy.filled_units // 2),
        seat="bot-06-exit",
    )
    assert sell.filled_units > 0
    # A mark taken before the sell is later than the priced tick, so a re-read of that
    # tick is refused by the ledger's mark-time guard. Assert the stamp directly.
    assert clock.now() > START
    assert adapter._last_price_ts[MINT] == START
