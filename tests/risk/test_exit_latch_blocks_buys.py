"""An observe-only EXIT seat refuses new buys desk-wide, even before its HaltSet is recorded."""

from __future__ import annotations

import random
from pathlib import Path

from pumpgrok.core.adapter import OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine import RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-101"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


def _engine(tmp_path: Path, clock: FixtureClock) -> RiskEngine:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )


def test_exit_latch_refuses_new_buys_before_its_halt_is_recorded(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    engine = _engine(tmp_path, clock)
    ids = IdFactory(clock, random.Random(9))
    engine.set_observe_only(frozenset({"bot-06-exit"}))
    buy = OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.BUY,
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        token_units=None,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )
    decision = engine.check(
        buy, seat="bot-04-sniper", source="paper", correlation_id="test", stage="ACCEPTED"
    )
    assert decision.passed is False
    assert decision.reason == "seat_may_trade"
