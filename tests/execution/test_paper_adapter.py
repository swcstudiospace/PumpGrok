"""Tracer: one curve BUY from reserves to FillRecorded (PAPER-001, R6, R38).

One BUY flows through RiskEngine.check, the shared OrderPlaced ledger
batch, seeded confirmation latency on virtual time, the CONFIRMING re-read
with stop re-checks, and lands as a curve-priced fill.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import buy_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine, order_hash_for

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
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


def _snap(s: int, t: int, *, complete: bool = False) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=s, t_units=t, complete=complete)


def _harness(
    tmp_path: Path, reads: list[CurveSnapshot], *, seed: int = 7, autonomy: str = "autonomous-paper"
) -> tuple[PaperAdapter, FixtureClock, OrderRequest]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(seed))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy=autonomy,  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(seed),
        price_source=ScriptedCurves(reads),
    )
    request = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )
    return adapter, clock, request


async def _place(adapter: PaperAdapter, clock: FixtureClock, request: OrderRequest) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def test_one_buy_flows_to_curve_priced_fill(tmp_path: Path) -> None:
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    fees = FeeModel()
    venue_fee = fees.venue_fee(SIZE)
    x_net = SIZE - venue_fee
    expected_out = buy_out(S0, T0, x_net)
    fill = await _place(adapter, clock, request)
    assert fill.status.value == "filled"
    assert fill.filled_lamports == SIZE
    assert fill.filled_units == expected_out
    assert fill.price_avg == Decimal(x_net) / Decimal(expected_out)
    assert fill.venue_fee_lamports == venue_fee
    assert fill.network_cost_lamports == fees.network_cost()
    assert fill.route == "curve"
    assert fill.venue_tx_ref.startswith("dry_run:")
    store = adapter._store
    placed = store.by_key(exec_place_key(request.ticket_id, "buy", request.decision_id))
    assert placed is not None
    quote = json.loads(str(placed["payload"]["quote_json"]))
    assert quote["source"] == "curve"
    assert quote["out_amount"] == expected_out
    fills = [e for e in store.read(limit=None) if e["type"] == "FillRecorded"]
    assert len(fills) == 1
    body = fills[0]["payload"]
    assert isinstance(body, dict)
    assert (body["curve_before_s"], body["curve_before_t"]) == (S0, T0)
    assert (body["curve_after_s"], body["curve_after_t"]) == (S0, T0)
    risk = json.loads(str(placed["payload"]["risk_json"]))
    assert risk["reason"] == "pass"
    assert risk["order_hash"] == order_hash_for(request)


async def test_repeated_decision_returns_first_fill(tmp_path: Path) -> None:
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    first = await _place(adapter, clock, request)
    second = await adapter.place(request, seat="bot-04-sniper", correlation_id="test")
    assert second.order_id == first.order_id
    fills = [e for e in adapter._store.read(limit=None) if e["type"] == "FillRecorded"]
    assert len(fills) == 1


async def test_no_fill_without_passing_risk_decision(tmp_path: Path) -> None:
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0)], autonomy="manual-ticket")
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError as exc:
        assert exc.reason == "approval_missing"
    else:
        raise AssertionError("manual-ticket buy without approval must refuse")
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds
    assert "OrderPlaced" not in kinds


async def test_quote_is_curve_sourced(tmp_path: Path) -> None:
    adapter, _clock, _request = _harness(tmp_path, [_snap(S0, T0)])
    quote = await adapter.quote("So11111111111111111111111111111111111111112", MINT, SIZE, 100)
    assert quote.source == "curve"
    assert quote.out_amount == buy_out(S0, T0, SIZE)
