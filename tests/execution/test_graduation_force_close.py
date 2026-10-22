"""INV-R-31 (graduation leg): force-close at the last curve price, freeze MTM."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 764_000_000_000_000
UNITS = 3_000_000
BASIS = 200_000_000


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _position(store: LedgerStore, clock: FixtureClock) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key="pos-graduated",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": MINT,
            "price_entry": "0.00001",
            "token_units": UNITS,
            "cost_basis_lamports": BASIS,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _adapter(store: LedgerStore, clock: FixtureClock, ids: IdFactory) -> PaperAdapter:
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(52)),
        clock=clock,
        autonomy="autonomous-paper",
        get_reserves=lambda _mint: (S0, T0),
        env={},
    )
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(52),
        budget=RiskBudget(),
        price_source=None,
        p_drop=0.0,
    )


async def test_graduation_closes_at_last_curve_price(tmp_path: Path) -> None:
    """INV-R-31: graduation force-closes at the last curve price; buys rejected after."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(52))
        _position(store, clock)
        adapter = _adapter(store, clock, ids)
        fees = FeeModel()
        row = await adapter.close_on_graduation(MINT, last_s=S0, last_t=T0, correlation_id="test")
        assert row is not None
        closed = store.read(types=["PositionClosed"], limit=None)
        assert len(closed) == 1
        payload = closed[0]["payload"]
        assert payload["reason"] == "graduated"
        gross = sell_out(S0, T0, UNITS)
        proceeds = gross - fees.venue_fee(gross) - fees.network_cost()
        assert payload["proceeds_lamports"] == proceeds
        assert payload["price_exit"] == str(Decimal(proceeds) / Decimal(UNITS))
        escalations = store.read(types=["Escalation"], limit=None)
        assert [e["payload"]["kind"] for e in escalations] == ["graduated"]
        repeat = await adapter.close_on_graduation(
            MINT, last_s=S0, last_t=T0, correlation_id="test"
        )
        assert repeat is None
        assert len(store.read(types=["PositionClosed"], limit=None)) == 1
    finally:
        store.close()


async def test_buy_on_graduated_curve_rejected(tmp_path: Path) -> None:
    """INV-R-31: a BUY on a complete curve is rejected post_graduation_no_reserves."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(52))
        adapter = _adapter(store, clock, ids)
        complete = CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, complete=True)

        class _Complete:
            async def curve(self, mint: str) -> CurveSnapshot | None:
                return complete

        adapter._price = _Complete()  # type: ignore[assignment]
        order = OrderRequest(
            ticket_id=TICKET,
            mint=MINT,
            side="buy",
            decision_id=ids.ulid(),
            size_lamports=BASIS,
            max_slippage_bps=100,
            approval_id=f"apr-{ids.ulid()}",
            correlation_id="test",
        )
        with pytest.raises(OrderRejectedError) as excinfo:
            await adapter.place(order, seat="bot-04-sniper")
        assert excinfo.value.reason == "post_graduation_no_reserves"
        assert excinfo.value.stage == "ACCEPTED"
    finally:
        store.close()
