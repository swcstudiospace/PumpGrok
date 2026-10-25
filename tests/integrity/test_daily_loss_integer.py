"""INT-03: the daily-loss halt compares integer lamports, never a float ratio.

The halt trips exactly at the configured fraction (integer cross
multiplication: ``loss * denom >= day_start * num``) and a non-positive
day-start equity fails the check with ``CorruptState`` instead of reading as
zero loss. Deterministic, no network.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.errors import CorruptState
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.reducer import initial_state
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT_A = "So11111111111111111111111111111111111111112"


def _store(tmp_path: Path, name: str, equity_meta: str) -> LedgerStore:
    path = tmp_path / name
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", equity_meta)
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock, **kwargs: Any) -> RiskEngine:
    kwargs.setdefault("get_reserves", lambda _mint: (42_000_000_000, 764_000_000_000_000))
    kwargs.setdefault("env", {})
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="autonomous-paper",
        **kwargs,
    )


def _buy(clock: FixtureClock, ids: IdFactory, mint: str = MINT_A) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=200_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def _fill(store: LedgerStore, clock: FixtureClock, ids: IdFactory, cash_delta: int) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"fill-{ids.ulid()}",
        type="FillRecorded",
        payload={
            "source": "paper",
            "order_id": ids.ulid(),
            "decision_id": ids.ulid(),
            "side": "sell",
            "mint": MINT_A,
            "filled_lamports": 0,
            "filled_units": 0,
            "filled_fraction": "1",
            "price_avg": "0.00001",
            "venue_fee_lamports": 0,
            "network_cost_lamports": 0,
            "cash_delta_lamports": cash_delta,
            "latency_s": "1.0",
            "venue_tx_ref": "",
        },
    )


def test_exact_boundary_trips_on_integer_math(tmp_path: Path) -> None:
    """A loss of exactly 5 % of day-start trips the halt (loss * 20 == start)."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path, "boundary.sqlite", str(EQUITY))
    try:
        ids = IdFactory(clock, make_rng(11))
        _fill(store, clock, ids, cash_delta=-500_000_000)
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.reason == "daily_loss_halt"
        assert len(store.read(types=["HaltSet"], limit=None)) == 1
    finally:
        store.close()


def test_one_lamport_below_boundary_does_not_trip(tmp_path: Path) -> None:
    """One lamport short of 5 % passes: 9_999_999_980 < 10_000_000_000."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path, "below.sqlite", str(EQUITY))
    try:
        ids = IdFactory(clock, make_rng(11))
        _fill(store, clock, ids, cash_delta=-499_999_999)
        engine = _engine(store, clock)
        decision = engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert decision.passed is True
        assert decision.reason == "pass"
        assert store.read(types=["HaltSet"], limit=None) == []
    finally:
        store.close()


def test_zero_start_equity_fails_the_check(tmp_path: Path) -> None:
    """Zero day-start equity raises; it is never zero loss."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path, "start-zero.sqlite", "0")
    try:
        ids = IdFactory(clock, make_rng(11))
        engine = _engine(store, clock)
        with pytest.raises(CorruptState, match="day-start equity"):
            engine.check(_buy(clock, ids), seat="bot-04-sniper")
        assert store.read(types=["HaltSet"], limit=None) == []
    finally:
        store.close()


def test_negative_start_equity_fails_the_check(tmp_path: Path) -> None:
    """A negative day-start baseline raises before any halt is evaluated."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path, "start-negative.sqlite", str(EQUITY))
    try:
        engine = _engine(store, clock)
        state = initial_state(source="paper", initial_equity_lamports=-1000, day_utc="2026-10-21")
        with pytest.raises(CorruptState, match="day-start equity"):
            engine._detect_breach(
                state,
                0,
                ts_utc="2026-10-21T00:00:00+00:00",
                source="paper",
                correlation_id="test",
            )
        assert store.read(types=["HaltSet"], limit=None) == []
    finally:
        store.close()
