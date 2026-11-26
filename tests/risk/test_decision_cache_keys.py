"""S-K6: a cached decision is never replayed across seats, creators, exit reasons or observe-only.

The decision cache key holds the seat, creator, exit reason, observe-only state and strategy id,
so each change re-runs the R34 walk.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine import RiskEngine

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
EQUITY = 10_000_000_000
MINT_A = "So11111111111111111111111111111111111111112"
BIG_RESERVES = (42_000_000_000, 764_000_000_000_000)


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        ids=IdFactory(clock, random.Random(11)),
        clock=clock,
        autonomy="manual-ticket",
        budget=RiskBudget(),
        get_reserves=lambda _mint: BIG_RESERVES,
    )


def _counting(engine: RiskEngine) -> list[int]:
    """Count the evaluations the engine runs; a cache hit runs none."""
    calls: list[int] = []
    real: Callable[..., Any] = engine._evaluate

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    engine._evaluate = counting  # type: ignore[method-assign]
    return calls


def _buy(ids: IdFactory) -> OrderRequest:
    return OrderRequest(
        ticket_id="SOL-20260201-001",
        mint=MINT_A,
        side="buy",
        decision_id=ids.ulid(),
        size_lamports=200_000_000,
        max_slippage_bps=50,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


def test_seat_change_is_evaluated_not_replayed(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, random.Random(7))
        engine = _engine(store, clock)
        calls = _counting(engine)
        order = _buy(ids)
        engine.check(order, seat="bot-04-sniper")
        engine.check(order, seat="bot-06-exit")
        assert len(calls) == 2
    finally:
        store.close()


def test_creator_change_is_evaluated_not_replayed(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, random.Random(7))
        engine = _engine(store, clock)
        calls = _counting(engine)
        order = _buy(ids)
        engine.check(order, seat="bot-04-sniper", creator="CreatorOne")
        engine.check(order, seat="bot-04-sniper", creator="CreatorTwo")
        assert len(calls) == 2
    finally:
        store.close()


def test_observe_only_change_is_evaluated_not_replayed(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, random.Random(7))
        engine = _engine(store, clock)
        calls = _counting(engine)
        order = _buy(ids)
        engine.check(order, seat="bot-04-sniper")
        engine.set_observe_only(frozenset({"bot-04-sniper"}))
        engine.check(order, seat="bot-04-sniper")
        assert len(calls) == 2
    finally:
        store.close()


def test_strategy_change_is_evaluated_not_replayed(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, random.Random(7))
        engine = _engine(store, clock)
        calls = _counting(engine)
        order = _buy(ids)
        engine.check(order, seat="bot-04-sniper", strategy_id="alpha")
        engine.check(order, seat="bot-04-sniper", strategy_id="beta")
        assert len(calls) == 2
    finally:
        store.close()
