"""Look-ahead canary: post-T extreme data never changes a decision at/before T."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def decide_at(events: Sequence[Mapping[str, Any]], ts: float) -> str:
    """Point-in-time decision: buy only on ticks stamped at or before ``ts``."""
    price = None
    for event in events:
        if float(event["ts"]) <= ts:
            price = int(event["price"])
    if price is None:
        return "hold"
    return "buy" if price >= 100 else "sell"


BASE = [
    {"ts": 1.0, "price": 90},
    {"ts": 2.0, "price": 95},
    {"ts": 3.0, "price": 110},
]


def test_extreme_future_never_changes_past_decision() -> None:
    before = {ts: decide_at(BASE, ts) for ts in (1.0, 2.0, 3.0)}
    extended = [*BASE, {"ts": 4.0, "price": 1}, {"ts": 5.0, "price": 99999}]
    after = {ts: decide_at(extended, ts) for ts in (1.0, 2.0, 3.0)}
    assert before == after
    assert before == {1.0: "sell", 2.0: "sell", 3.0: "buy"}


def test_future_extremes_change_only_future_decisions() -> None:
    extended = [*BASE, {"ts": 4.0, "price": 1}, {"ts": 5.0, "price": 99999}]
    assert decide_at(extended, 4.0) == "sell"
    assert decide_at(extended, 5.0) == "buy"
