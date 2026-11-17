"""Look-ahead canary: data after time T does not change a decision at or before T (BT-10)."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Sequence

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.strategies.base import Intent, TickSnapshot
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.runtime import StrategyRuntime

_MINT = "MintLookahead"


def _events() -> list[dict[str, object]]:
    """A breakout before T and a stop after T. Future rows are the ones the canary mutates."""
    return [
        {"mint": _MINT, "ts": 0.0, "price": 1_000, "liquidity": 50, "side": "buy"},
        {"mint": _MINT, "ts": 10.0, "price": 1_000, "liquidity": 50, "side": "buy"},
        {"mint": _MINT, "ts": 20.0, "price": 1_300, "liquidity": 40, "side": "buy"},
        {"mint": _MINT, "ts": 400.0, "price": 100, "liquidity": 30, "side": "sell"},
        {"mint": _MINT, "ts": 500.0, "price": 100, "liquidity": 30, "side": "sell"},
    ]


def _mutate_after(events: Sequence[dict[str, object]], cutoff: float) -> list[dict[str, object]]:
    mutated = copy.deepcopy(list(events))
    for event in mutated:
        if float(event["ts"]) <= cutoff:
            continue
        event["price"] = int(event["price"]) * 1000
        event["liquidity"] = 0
        event["side"] = "buy" if event["side"] == "sell" else "sell"
    return mutated


def _ticks(events: Sequence[dict[str, object]]) -> list[TickSnapshot]:
    return [
        TickSnapshot(
            mint=str(event["mint"]),
            ts=float(event["ts"]),
            launch_ts=0.0,
            price_lamports=int(event["price"]),
            unique_buyers=1,
            curve_progress=0.1,
        )
        for event in events
    ]


def _run(events: Sequence[dict[str, object]]) -> tuple[tuple[float, Intent], ...]:
    found: list[tuple[float, Intent]] = []

    async def sink(intents: tuple[Intent, ...]) -> None:
        found.extend((intent_ts(intent), intent) for intent in intents)

    async def drive() -> None:
        runtime = StrategyRuntime(
            clock=FixtureClock(0.0),
            strategies=(MomentumBreakout(),),
            sink=sink,
        )
        await runtime.run(_ticks(events))

    asyncio.run(drive())
    return tuple(found)


def intent_ts(intent: Intent) -> float:
    return float(intent.decision_id.rsplit(":", 1)[-1])


def _at_or_before(
    rows: Sequence[tuple[float, Intent]], cutoff: float
) -> tuple[tuple[float, str, str, int, str], ...]:
    return tuple(
        (ts, intent.side, intent.mint, intent.size_lamports, intent.reason)
        for ts, intent in rows
        if ts <= cutoff
    )


def test_extreme_future_does_not_change_decisions_at_or_before_t() -> None:
    base = _events()
    original = _run(base)
    cutoffs = (0.0, 20.0, 100.0)
    assert any(ts <= 20.0 for ts, _ in original)
    saw_future_change = False
    for cutoff in cutoffs:
        mutated_events = _mutate_after(base, cutoff)
        assert any(event["ts"] > cutoff and event["liquidity"] == 0 for event in mutated_events)
        extreme = any(
            event["ts"] > cutoff and int(event["price"]) >= 100_000 for event in mutated_events
        )
        assert extreme
        mutated = _run(mutated_events)
        assert _at_or_before(original, cutoff) == _at_or_before(mutated, cutoff)
        if _at_or_before(original, 10**9) != _at_or_before(mutated, 10**9):
            saw_future_change = True
    assert saw_future_change
