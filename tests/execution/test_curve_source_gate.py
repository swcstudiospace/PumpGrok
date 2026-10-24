"""Entry gate checks each snapshot's own source; exposure follows reducer cost basis.

RPC-derived reserves are refused with ``data_unavailable`` while the curve
layout is ASSUMED, decided per snapshot rather than by a constructor value.
Exposure after a partial sell reports the cost basis the reducer keeps.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools._common import fold_current_state
from pumpgrok.tools.portfolio.exposure import ExposureIn, run_exposure

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-101"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


class ScriptedCurves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _harness(tmp_path: Path, reads: list[CurveSnapshot]) -> tuple[PaperAdapter, FixtureClock]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(7))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=ScriptedCurves(reads),
        p_drop=0.0,
    )
    return adapter, clock


def _request(adapter: PaperAdapter, ticket: str, *, side: Side, units: int | None) -> OrderRequest:
    buy = side is Side.BUY
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT,
        side=side,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE if buy else None,
        token_units=None if buy else units,
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


async def test_rpc_entry_snapshot_is_refused_at_accepted(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap("rpc"), _snap("rpc")])
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    rejected = adapter._store.read(types=["OrderRejected"], limit=None)
    assert [row["payload"]["stage"] for row in rejected] == ["ACCEPTED"]
    assert rejected[0]["payload"]["reason"] == "data_unavailable"
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "OrderPlaced" not in kinds
    assert "FillRecorded" not in kinds


async def test_rpc_confirmation_snapshot_is_refused_at_confirming(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap("fixture"), _snap("rpc")])
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    rejected = adapter._store.read(types=["OrderRejected"], limit=None)
    assert [row["payload"]["stage"] for row in rejected] == ["CONFIRMING"]
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds


async def test_exposure_after_partial_sell_matches_reducer_cost_basis(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap("fixture")] * 5)
    buy_request = _request(adapter, TICKET, side=Side.BUY, units=None)
    buy = await _place(adapter, clock, buy_request, seat="bot-04-sniper")
    units = buy.filled_units
    opened_cost = adapter._store.read(types=["PositionOpened"], limit=None)[0]["payload"][
        "cost_basis_lamports"
    ]

    clock.advance_to(clock.now() + 5.0)
    await adapter.mark_open_positions(correlation_id="test")
    sell_request = _request(adapter, "SOL-20260201-102", side=Side.SELL, units=units // 2)
    await _place(adapter, clock, sell_request, seat="bot-06-exit")

    state = fold_current_state(adapter._store, clock)
    reducer_basis = state.positions[MINT].cost_basis_lamports
    assert 0 < reducer_basis < opened_cost

    out = await run_exposure(ExposureIn(mint=MINT), adapter._store, clock)
    assert out["per_token"] == [{"mint": MINT, "exposure_lamports": reducer_basis}]
    assert out["gross_exposure_lamports"] == reducer_basis
