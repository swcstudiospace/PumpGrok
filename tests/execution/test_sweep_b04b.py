"""Sweep B04b regression tests (bot-04-sniper, EXEC-EX-*).

Each test pins one fix from the execution sweep register and fails on the
base commit where the behavior was wrong. No replay fixtures are re-pinned.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.sources import FixtureCurveSource
from pumpgrok.risk.engine import RiskEngine

from .replay_support import replay_authority, tick

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
OTHER = "So22222222222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


def _harness(
    tmp_path: Path,
    *,
    curve_ticks: list[dict[str, Any]] | None = None,
    seed: int = 7,
    p_drop: float = 0.0,
    size: int = SIZE,
    side: Side = Side.BUY,
    ticket: str = TICKET,
) -> tuple[PaperAdapter, FixtureClock, OrderRequest]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "replay")
    ids = IdFactory(clock, make_rng(seed))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    ticks = curve_ticks if curve_ticks is not None else [tick(START, MINT, S0, T0)]
    replay = replay_authority(tmp_path, clock, ticks)
    adapter = build_paper_adapter(
        SimpleNamespace(risk=RiskBudget()),
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(seed),
        replay=replay,
        source="replay",
        p_drop=p_drop,
    )
    request = OrderRequest(
        ticket_id=ticket,
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
) -> Any:
    task = asyncio.create_task(adapter.place(request, seat=seat, correlation_id="test"))
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _placed_order_id(adapter: PaperAdapter) -> str:
    placed = [e for e in adapter._store.read(limit=None) if e["type"] == "OrderPlaced"]
    assert len(placed) == 1
    payload = placed[0]["payload"]
    assert isinstance(payload, dict)
    return str(payload["order_id"])


def _seed_position(
    store: LedgerStore, clock: FixtureClock, mint: str, units: int, basis: int, key: str
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=key,
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": mint,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": basis,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


async def test_cancel_after_latency_returns_false(tmp_path: Path) -> None:
    """EX-03: cancel once the latency sleep has completed must return False."""
    monkeypatch = pytest.MonkeyPatch()
    gate = asyncio.Event()
    reads = {"n": 0}
    real = FixtureCurveSource.curve

    async def blocking(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        reads["n"] += 1
        if reads["n"] == 2:
            await gate.wait()
        return await real(self, mint)

    monkeypatch.setattr(FixtureCurveSource, "curve", blocking)
    try:
        adapter, clock, request = _harness(tmp_path)
        task = asyncio.create_task(
            adapter.place(request, seat="bot-04-sniper", correlation_id="test")
        )
        for _ in range(400):
            if reads["n"] >= 2:
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert reads["n"] >= 2, "CONFIRMING read must be reached"
        order_id = _placed_order_id(adapter)
        # The latency sleep has completed (the CONFIRMING read is in flight):
        # cancel must refuse instead of claiming success.
        assert await adapter.cancel(order_id, request.ticket_id, request.decision_id) is False
        gate.set()
        for _ in range(400):
            if task.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        fill = await task
        assert fill.status.value == "filled"
    finally:
        monkeypatch.undo()


async def test_mark_to_market_refuses_untrusted_curve(tmp_path: Path) -> None:
    """EX-01: the single-mint mark passes the same admission gate as batch marks."""
    adapter, clock, request = _harness(tmp_path)
    await _place(adapter, clock, request)
    real = FixtureCurveSource.curve

    async def rogue(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        snap = await real(self, mint)
        if snap is None:
            return None
        return snap.model_copy(update={"source": "rogue"})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(FixtureCurveSource, "curve", rogue)
    try:
        assert await adapter.mark_to_market(MINT, correlation_id="test") is None
    finally:
        monkeypatch.undo()


async def test_live_value_falls_back_when_curve_refused(tmp_path: Path) -> None:
    """EX-02: a refused live curve in close_position falls back to last-good."""
    adapter, clock, request = _harness(tmp_path)
    fill = await _place(adapter, clock, request)
    assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
    pos = adapter._fold_state().positions[MINT]
    last_mtm = int(pos.last_mtm_lamports)
    assert last_mtm > 0
    rogue = CurveSnapshot(mint=MINT, s_lamports=10**15, t_units=10**15, source="rogue")
    valued = adapter._live_value(MINT, pos, rogue)
    assert valued is not None
    network = adapter._fees.network_cost()
    assert valued.proceeds == max(last_mtm - network, 0)
    curve_exit = adapter._curve_exit(MINT, 10**15, 10**15, int(fill.filled_units))
    assert valued.proceeds != curve_exit.proceeds


def test_curve_exit_floors_proceeds_at_zero(tmp_path: Path) -> None:
    """EX-08: a dust exit whose fees exceed its gross books zero proceeds."""
    adapter, _clock, _request = _harness(tmp_path)
    valued = adapter._curve_exit(MINT, S0, T0, 1)
    assert valued.proceeds == 0
    # The shortfall stays visible: the fees were charged, the proceeds are zero.
    assert valued.venue_fee + valued.network_cost > 0


async def test_reentry_charges_rent_again(tmp_path: Path) -> None:
    """EX-06: close refunds the rent; the next entry pays it again."""
    adapter, clock, buy1 = _harness(tmp_path)
    first = await _place(adapter, clock, buy1)
    expected_first = adapter._fees.buy_network_cost(first_buy=True)
    assert first.network_cost_lamports == expected_first
    # The risk gate admits a SELL only on a MarkToMarket younger than mtm_interval_s.
    assert await adapter.mark_to_market(MINT, correlation_id="test") is not None
    sell_request = OrderRequest(
        ticket_id="SOL-20260201-002",
        mint=MINT,
        side=Side.SELL,
        decision_id=adapter._ids.ulid(),
        token_units=first.filled_units,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    await _place(adapter, clock, sell_request, seat="bot-06-exit")
    buy2 = OrderRequest(
        ticket_id="SOL-20260201-003",
        mint=MINT,
        side=Side.BUY,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    second = await _place(adapter, clock, buy2)
    assert second.network_cost_lamports == expected_first


async def test_one_mint_failure_does_not_abort_batch(tmp_path: Path) -> None:
    """EX-20: a failing curve read for one mint keeps that mint's last mark."""
    ticks = [tick(START, MINT, S0, T0), tick(START, OTHER, S0, T0)]
    adapter, clock, _request = _harness(tmp_path, curve_ticks=ticks)
    _seed_position(adapter._store, clock, MINT, 3_000_000, 200_000_000, "pos-a")
    _seed_position(adapter._store, clock, OTHER, 1_000_000, 50_000_000, "pos-b")
    real = FixtureCurveSource.curve

    async def flaky(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        if mint == OTHER:
            raise RuntimeError("curve source down")
        return await real(self, mint)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(FixtureCurveSource, "curve", flaky)
    try:
        row = await adapter.mark_open_positions(correlation_id="test")
        assert row is not None
        payload = json.loads(row["payload_json"])
        assert isinstance(payload, dict)
        prices = payload["prices_json"]
        assert MINT in prices
    finally:
        monkeypatch.undo()


async def test_zero_confirm_output_rejects_before_division(tmp_path: Path) -> None:
    """EX-21: a CONFIRMING curve that yields zero units is refused, not divided."""
    real = FixtureCurveSource.curve

    async def dusty(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        snap = await real(self, mint)
        if snap is None:
            return None
        return snap.model_copy(update={"s_lamports": 10**18, "t_units": 1})

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(FixtureCurveSource, "curve", dusty)
    try:
        adapter, clock, request = _harness(tmp_path)
        try:
            await _place(adapter, clock, request)
        except OrderRejectedError as exc:
            assert exc.reason == "zero_output"
            assert exc.stage == "CONFIRMING"
        else:
            raise AssertionError("zero CONFIRMING output must refuse")
        rows = adapter._store.read(limit=None)
        assert any(
            e["type"] == "OrderRejected"
            and isinstance(e["payload"], dict)
            and e["payload"].get("reason") == "zero_output"
            for e in rows
        )
    finally:
        monkeypatch.undo()


async def test_simulate_buy_preview_includes_rent(tmp_path: Path) -> None:
    """EX-22: simulate BUY network cost matches the fill cost on a flat mint."""
    adapter, _clock, request = _harness(tmp_path)
    sim = await adapter.simulate(
        mint=request.mint,
        side=request.side,
        size_lamports=request.size_lamports,
        token_units=request.token_units,
    )
    assert sim.would_fill is True
    assert sim.network_cost_lamports == adapter._fees.buy_network_cost(first_buy=True)
    assert adapter._store.read(limit=None) == []


async def test_simulate_rejects_non_positive_size(tmp_path: Path) -> None:
    """EX-23: a zero size is a non-fill, never a bare error or a zero fill."""
    adapter, _clock, request = _harness(tmp_path)
    sim = await adapter.simulate(
        mint=request.mint, side=Side.BUY, size_lamports=0, token_units=None
    )
    assert sim.would_fill is False
    assert sim.fill_kind == "rejected"


async def test_quote_rejects_out_of_range_slippage(tmp_path: Path) -> None:
    """EX-24: slippage_bps outside 0..10000 is refused at the boundary."""
    adapter, _clock, _request = _harness(tmp_path)
    for bad in (-1, 10_001):
        try:
            await adapter.quote("So11111111111111111111111111111111111111112", MINT, SIZE, bad)
        except OrderRejectedError as exc:
            assert exc.reason == "invalid_slippage"
        else:
            raise AssertionError(f"slippage_bps={bad} must refuse")


async def test_positions_surfaces_unparseable_opened_at(tmp_path: Path) -> None:
    """EX-26: a corrupt opened_ts_utc is surfaced, never replaced with now."""
    adapter, clock, _request = _harness(tmp_path)
    store = adapter._store
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="pos-bad",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00001",
            "token_units": 1_000,
            "cost_basis_lamports": 100,
            "opened_ts_utc": "not-a-timestamp",
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )
    with pytest.raises(ValueError):
        await adapter.positions()


async def test_sell_price_avg_is_net_of_venue_fee(tmp_path: Path) -> None:
    """EXEC-D-27 net basis: the SELL fill prices like the BUY fill, venue-net."""
    adapter, clock, buy_request = _harness(tmp_path)
    buy = await _place(adapter, clock, buy_request)
    await adapter.mark_to_market(MINT, correlation_id="test")
    sell_request = OrderRequest(
        ticket_id="SOL-20260201-002",
        mint=MINT,
        side=Side.SELL,
        decision_id=adapter._ids.ulid(),
        token_units=buy.filled_units,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )
    sell = await _place(adapter, clock, sell_request, seat="bot-06-exit")
    gross = sell_out(S0, T0, buy.filled_units)
    venue = adapter._fees.venue_fee(gross)
    assert sell.price_avg == Decimal(gross - venue) / Decimal(buy.filled_units)


async def test_sell_confirm_read_failure_records_rejection(tmp_path: Path) -> None:
    """EX-29: a SELL CONFIRMING read failure records its rejection outcome."""
    monkeypatch = pytest.MonkeyPatch()
    adapter, clock, buy_request = _harness(tmp_path)
    buy = await _place(adapter, clock, buy_request)
    await adapter.mark_to_market(MINT, correlation_id="test")
    real = FixtureCurveSource.curve
    reads = {"n": 0}

    async def flaky(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        reads["n"] += 1
        if reads["n"] >= 2:
            raise RuntimeError("confirming read down")
        return await real(self, mint)

    monkeypatch.setattr(FixtureCurveSource, "curve", flaky)
    try:
        sell_request = OrderRequest(
            ticket_id="SOL-20260201-002",
            mint=MINT,
            side=Side.SELL,
            decision_id=adapter._ids.ulid(),
            token_units=buy.filled_units,
            max_slippage_bps=100,
            approval_id=f"apr-{adapter._ids.ulid()}",
            correlation_id="test",
        )
        try:
            await _place(adapter, clock, sell_request, seat="bot-06-exit")
        except OrderRejectedError as exc:
            assert exc.reason == "data_unavailable"
            assert exc.stage == "CONFIRMING"
        else:
            raise AssertionError("SELL CONFIRMING read failure must refuse with a recorded outcome")
        rejects = [e for e in adapter._store.read(limit=None) if e["type"] == "OrderRejected"]
        assert any(
            isinstance(e["payload"], dict) and e["payload"].get("reason") == "data_unavailable"
            for e in rejects
        )
    finally:
        monkeypatch.undo()


async def test_repeated_decision_returns_first_outcome(tmp_path: Path) -> None:
    """EX-31 (repeat path): a repeated decision replays its first Fill."""
    adapter, clock, request = _harness(tmp_path)
    first = await _place(adapter, clock, request)
    repeated = await _place(adapter, clock, request)
    assert repeated == first
