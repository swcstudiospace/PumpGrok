"""STR-04: momentum_breakout flips exactly at its threshold bound."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.momentum_breakout import MomentumBreakoutStrategy
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick, load_tape

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "strat-breakout"


def _run(ticks: list[Tick]) -> list:
    strategy = MomentumBreakoutStrategy({"breakout_bps": 1000})
    allocation = Allocation(10_000_000, {"momentum_breakout": 10_000_000})
    return StrategyRuntime(
        Tape.from_ticks(ticks), {"momentum_breakout": strategy}, allocation
    ).run()


def test_one_tick_below_no_fire_at_bound_fire() -> None:
    below = [
        Tick(ts=1.0, mint="M", price_lamports=100_000),
        Tick(ts=2.0, mint="M", price_lamports=109_999),
    ]
    at = [
        Tick(ts=1.0, mint="M", price_lamports=100_000),
        Tick(ts=2.0, mint="M", price_lamports=110_000),
    ]
    assert _run(below) == []
    intents = _run(at)
    assert len(intents) == 1
    assert intents[0].side == "buy" and intents[0].mint == "M"


def test_fixture_produces_one_asserted_fill() -> None:
    tape = load_tape(FIXTURE)
    strategy = MomentumBreakoutStrategy({"breakout_bps": 1000})
    allocation = Allocation(10_000_000, {"momentum_breakout": 10_000_000})
    intents = StrategyRuntime(tape, {"momentum_breakout": strategy}, allocation).run()
    assert len(intents) == 1
    assert intents[0].mint == "BreakMint1111111111111111111111111111111"
    # The prefix without the firing tick produces no fill.
    strategy2 = MomentumBreakoutStrategy({"breakout_bps": 1000})
    allocation2 = Allocation(10_000_000, {"momentum_breakout": 10_000_000})
    runtime2 = StrategyRuntime(
        Tape.from_ticks(list(tape.ticks[:2])),
        {"momentum_breakout": strategy2},
        allocation2,
    )
    assert runtime2.run() == []


def test_look_ahead_canary() -> None:
    """A huge future tick cannot move any earlier decision."""
    prefix = [
        Tick(ts=1.0, mint="M", price_lamports=100_000),
        Tick(ts=2.0, mint="M", price_lamports=109_900),
    ]
    full = [*prefix, Tick(ts=3.0, mint="M", price_lamports=999_999)]
    assert _run(prefix) == []
    intents = _run(full)
    assert len(intents) == 1  # only the spike tick fires


def test_params_validated_against_bounds() -> None:
    with pytest.raises(ValueError):
        MomentumBreakoutStrategy({"breakout_bps": 10_001})
    with pytest.raises(ValueError):
        MomentumBreakoutStrategy({})
    assert MomentumBreakoutStrategy({"breakout_bps": 0}).BOUNDS == {"breakout_bps": (0, 10000)}
