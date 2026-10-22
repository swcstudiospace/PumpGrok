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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import buy_out, sell_out
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
    tmp_path: Path,
    reads: list[CurveSnapshot],
    *,
    seed: int = 7,
    autonomy: str = "autonomous-paper",
    budget: RiskBudget | None = None,
    p_drop: float = 0.0,
    size: int = SIZE,
    side: Side = Side.BUY,
) -> tuple[PaperAdapter, FixtureClock, OrderRequest]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(seed))
    engine = RiskEngine(
        store=store,
        budget=budget if budget is not None else RiskBudget(),
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
        budget=budget if budget is not None else RiskBudget(),
        price_source=ScriptedCurves(reads),
        p_drop=p_drop,
    )
    request = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=side,
        decision_id=ids.ulid(),
        size_lamports=size if side is Side.BUY else None,
        token_units=size if side is Side.SELL else None,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )
    return adapter, clock, request


async def _place(
    adapter: PaperAdapter,
    clock: FixtureClock,
    request: OrderRequest,
    *,
    seat: str = "bot-04-sniper",
) -> Fill:
    task = asyncio.create_task(adapter.place(request, seat=seat, correlation_id="test"))
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


BIG = RiskBudget(
    max_trade_fraction=Decimal("1"),
    max_token_fraction=Decimal("1"),
    daily_loss_halt_fraction=Decimal("0.05"),
    drawdown_halt_fraction=Decimal("0.15"),
    max_open_positions=100,
    max_trades_per_day=1000,
    liquidity_floor_multiple=10,
    partial_fill_fraction=Decimal("0.02"),
)


async def test_full_fill_at_l_over_50(tmp_path: Path) -> None:
    size = S0 * 2 // 100
    adapter, clock, request = _harness(
        tmp_path, [_snap(S0, T0), _snap(S0, T0)], budget=BIG, size=size
    )
    fill = await _place(adapter, clock, request)
    assert fill.status.value == "filled"
    assert fill.filled_lamports == size
    assert fill.filled_fraction == Decimal("1")


async def test_partial_fill_between_l_over_50_and_l_over_10(tmp_path: Path) -> None:
    size = S0 * 2 // 100 + 660_000_000
    assert S0 // 50 < size <= S0 // 10
    adapter, clock, request = _harness(
        tmp_path, [_snap(S0, T0), _snap(S0, T0)], budget=BIG, size=size
    )
    fill = await _place(adapter, clock, request)
    cap = S0 * 2 // 100
    assert fill.status.value == "partial"
    assert fill.filled_lamports == cap
    assert fill.filled_fraction == Decimal(cap) / Decimal(size)
    placed = [e for e in adapter._store.read(limit=None) if e["type"] == "OrderPlaced"]
    assert len(placed) == 1


async def test_below_liquidity_floor_rejects(tmp_path: Path) -> None:
    size = S0 // 10 + 1
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0)], budget=BIG, size=size)
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError as exc:
        assert exc.reason == "below_liquidity_floor"
        assert exc.fees_lamports == 0
    else:
        raise AssertionError("order above S0/10 must refuse")
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds


async def test_slippage_exceeded_charges_only_network_cost(tmp_path: Path) -> None:
    fees = FeeModel()
    big_s1 = S0 + S0 // 20
    k = S0 * T0
    t1 = k // big_s1
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0), _snap(big_s1, t1)])
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError as exc:
        assert exc.reason == "slippage_exceeded"
        assert exc.stage == "CONFIRMING"
        assert exc.fees_lamports == fees.network_cost()
    else:
        raise AssertionError("moved curve must refuse with slippage_exceeded")
    rows = adapter._store.read(limit=None)
    assert not [e for e in rows if e["type"] == "FillRecorded"]
    rejects = [e for e in rows if e["type"] == "OrderRejected"]
    assert len(rejects) == 1
    body = rejects[0]["payload"]
    assert isinstance(body, dict)
    assert body["fees_lamports"] == fees.network_cost()
    assert body["confirm_out"] < body["other_amount_threshold"]


async def test_tx_dropped_changes_no_balances(tmp_path: Path) -> None:
    adapter, clock, request = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)], p_drop=1.0)
    try:
        await _place(adapter, clock, request)
    except OrderRejectedError as exc:
        assert exc.reason == "tx_dropped"
        assert exc.fees_lamports == 0
    else:
        raise AssertionError("p_drop=1.0 must refuse with tx_dropped")
    rows = adapter._store.read(limit=None)
    assert not [e for e in rows if e["type"] == "FillRecorded"]
    assert not [e for e in rows if e["type"] == "PositionOpened"]


async def test_same_seed_replays_identically(tmp_path: Path, tmp_path_factory: Any) -> None:
    other = tmp_path_factory.mktemp("replay")
    first_adapter, first_clock, first_request = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    second_adapter, second_clock, second_request = _harness(other, [_snap(S0, T0), _snap(S0, T0)])
    first = await _place(first_adapter, first_clock, first_request)
    second = await _place(second_adapter, second_clock, second_request)
    assert first == second
    first_hashes = [e["hash"] for e in first_adapter._store.read(limit=None)]
    second_hashes = [e["hash"] for e in second_adapter._store.read(limit=None)]
    assert first_hashes == second_hashes


async def test_sell_mirrors_buy_through_sell_out(tmp_path: Path) -> None:
    adapter, clock, buy_request = _harness(
        tmp_path,
        [_snap(S0, T0), _snap(S0, T0), _snap(S0, T0), _snap(S0, T0), _snap(S0, T0)],
    )
    buy = await _place(adapter, clock, buy_request)
    assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
    units = buy.filled_units
    sell_request = OrderRequest(
        ticket_id="SOL-20260201-002",
        mint=MINT,
        side=Side.SELL,
        decision_id=adapter._ids.ulid(),
        token_units=units,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    sell = await _place(adapter, clock, sell_request, seat="bot-06-exit")
    fees = FeeModel()
    gross = sell_out(S0, T0, units)
    assert sell.filled_units == units
    assert sell.filled_lamports == gross - fees.venue_fee(gross) - fees.network_cost()
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "PositionClosed" in kinds


async def test_simulate_previews_full_without_writes(tmp_path: Path) -> None:
    adapter, _clock, request = _harness(tmp_path, [_snap(S0, T0)])
    sim = await adapter.simulate(
        mint=request.mint,
        side=request.side,
        size_lamports=request.size_lamports,
        token_units=request.token_units,
    )
    assert sim.would_fill is True
    assert sim.fill_kind == "full"
    assert adapter._store.read(limit=None) == []


async def test_repeated_risk_refusal_replays_first_refusal(tmp_path: Path) -> None:
    """CR-02: retrying a risk-refused order replays the stored refusal.

    An ACCEPTED-stage refusal writes no OrderPlaced row, so the retry reaches
    ``_reject`` with the identical key. The second attempt must raise the
    same ``OrderRejectedError`` (never a raw ``sqlite3.IntegrityError``) and
    must not append a second ``OrderRejected`` row.
    """
    adapter, _clock, request = _harness(tmp_path, [_snap(S0, T0)], autonomy="manual-ticket")
    try:
        await adapter.place(request, seat="bot-04-sniper", correlation_id="test")
    except OrderRejectedError as exc:
        assert exc.reason == "approval_missing"
    else:
        raise AssertionError("manual-ticket buy without approval must refuse")
    try:
        await adapter.place(request, seat="bot-04-sniper", correlation_id="test")
    except OrderRejectedError as exc:
        assert exc.reason == "approval_missing"
        assert exc.stage == "ACCEPTED"
    else:
        raise AssertionError("retry of a refused decision must refuse again")
    rejects = [e for e in adapter._store.read(limit=None) if e["type"] == "OrderRejected"]
    assert len(rejects) == 1
    assert rejects[0]["payload"]["decision_id"] == request.decision_id
