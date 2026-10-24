"""Graduation, blind flatten, R65 probe record, fail-closed gate (PAPER-005).

A BUY on a complete curve rejects with post_graduation_no_reserves. Curve
completion force-closes the open position at the last pre-graduation
sell_out with reason graduated, a frozen mark, and an Escalation. A 300
virtual-second silence without a price force-closes at last_good with
reason blind_flatten and an Escalation. While the bonding-curve layout
fixture is ASSUMED, RPC-derived entries refuse with data_unavailable.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import (
    CurveSnapshot,
    OrderRejectedError,
    PaperAdapter,
)
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.onchain.curve_layout import LAYOUT_STATUS, rpc_curve_price_allowed

START = 1_769_900_000.0
EQUITY = 10_000_000_000
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


def _snap(s: int, t: int, *, complete: bool = False) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=s, t_units=t, complete=complete)


class _Scripted:
    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _harness(tmp_path: Path, reads: list[CurveSnapshot]) -> tuple[PaperAdapter, FixtureClock]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(9))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(9)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(9),
        price_source=_Scripted(reads),
    )
    return adapter, clock


async def _buy(adapter: PaperAdapter, clock: FixtureClock, ticket: str) -> Fill:
    request = OrderRequest(
        ticket_id=ticket,
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


async def test_graduated_buy_is_rejected(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap(S0, T0, complete=True)])
    request = OrderRequest(
        ticket_id="SOL-20260201-010",
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    with pytest.raises(OrderRejectedError) as exc_info:
        await task
    assert exc_info.value.reason == "post_graduation_no_reserves"
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds
    assert "OrderPlaced" not in kinds


async def test_graduation_close_uses_last_pre_graduation_sell_out(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    fill = await _buy(adapter, clock, "SOL-20260201-011")
    units = fill.filled_units
    closed = await adapter.close_on_graduation(MINT, last_s=S0, last_t=T0)
    assert closed is not None
    fees = FeeModel()
    gross = sell_out(S0, T0, units)
    expected = gross - fees.venue_fee(gross) - fees.network_cost()
    body = json.loads(str(closed["payload_json"]))
    assert body["reason"] == "graduated"
    assert body["proceeds_lamports"] == expected
    assert adapter.frozen_mark(MINT) == expected
    rows = adapter._store.read(limit=None)
    escalations = [e for e in rows if e["type"] == "Escalation"]
    assert len(escalations) == 1
    detail = escalations[0]["payload"]
    assert isinstance(detail, dict)
    assert detail["kind"] == "graduated"
    assert "frozen=true" in str(detail["detail"])


async def test_graduation_close_without_position_is_noop(tmp_path: Path) -> None:
    adapter, _clock = _harness(tmp_path, [_snap(S0, T0)])
    assert await adapter.close_on_graduation(MINT, last_s=S0, last_t=T0) is None
    assert adapter._store.read(limit=None) == []


async def test_blind_timeout_closes_at_last_good(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    fill = await _buy(adapter, clock, "SOL-20260201-012")
    assert fill.filled_units > 0
    marked = await adapter.mark_to_market(MINT, correlation_id="test")
    assert marked is not None
    mark_body = json.loads(str(marked["payload_json"]))
    last_good = int(mark_body["equity_lamports"]) - int(mark_body["cash_lamports"])
    clock.advance_to(clock.now() + 301.0)
    closed = await adapter.check_blind(MINT, correlation_id="test")
    assert closed is not None
    body = json.loads(str(closed["payload_json"]))
    assert body["reason"] == "blind_flatten"
    assert body["proceeds_lamports"] == last_good - FeeModel().network_cost()
    assert adapter.frozen_mark(MINT) == last_good - FeeModel().network_cost()
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "Escalation" in kinds


async def test_blind_before_timeout_keeps_position(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    await _buy(adapter, clock, "SOL-20260201-013")
    clock.advance_to(clock.now() + 299.0)
    assert await adapter.check_blind(MINT, correlation_id="test") is None


async def test_mark_to_market_values_liquidation_every_60s(tmp_path: Path) -> None:
    adapter, clock = _harness(tmp_path, [_snap(S0, T0), _snap(S0, T0)])
    fill = await _buy(adapter, clock, "SOL-20260201-014")
    clock.advance_to(clock.now() + 60.0)
    row = await adapter.mark_to_market(MINT, correlation_id="test")
    assert row is not None
    body = json.loads(str(row["payload_json"]))
    fees = FeeModel()
    gross = sell_out(S0, T0, fill.filled_units)
    assert body["equity_lamports"] - body["cash_lamports"] == gross - fees.venue_fee(gross)
    marks = json.loads(str(body["prices_json"]))
    assert marks[MINT]["source"] == "curve"


async def test_assumed_layout_refuses_rpc_entries(tmp_path: Path) -> None:
    assert LAYOUT_STATUS == "ASSUMED"
    assert rpc_curve_price_allowed(curve_source="rpc") is False
    assert rpc_curve_price_allowed(curve_source="fixture") is True
    rpc_snap = _snap(S0, T0).model_copy(update={"source": "rpc"})
    adapter, clock = _harness(tmp_path, [rpc_snap, rpc_snap])
    request = OrderRequest(
        ticket_id="SOL-20260201-015",
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    with pytest.raises(OrderRejectedError) as exc_info:
        await task
    assert exc_info.value.reason == "data_unavailable"
    kinds = [e["type"] for e in adapter._store.read(limit=None)]
    assert "OrderPlaced" not in kinds
    assert "FillRecorded" not in kinds


def test_layout_fixture_matches_code_status() -> None:
    fixture = Path("tests/fixtures/rpc/bonding_curve/layout.json")
    record = json.loads(fixture.read_text(encoding="utf-8"))
    assert record["layout_status"] == LAYOUT_STATUS == "ASSUMED"
    assert record["layout_status"] != "VERIFIED"
    assert "probe_error" in record
