"""STR-04: mean_reversion flips exactly at its deviation bound."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.mean_reversion import MeanReversionStrategy
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick, load_tape

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "strat-reversion"


def _run(ticks: list[Tick], deviation: int = 1000) -> list:
    strategy = MeanReversionStrategy({"deviation_bps": deviation})
    allocation = Allocation(10_000_000, {"mean_reversion": 10_000_000})
    return StrategyRuntime(Tape.from_ticks(ticks), {"mean_reversion": strategy}, allocation).run()


def _ticks(third: int) -> list[Tick]:
    return [
        Tick(ts=1.0, mint="M", price_lamports=10_000),
        Tick(ts=2.0, mint="M", price_lamports=10_100),
        Tick(ts=3.0, mint="M", price_lamports=third),
    ]


def test_one_tick_below_no_fire_at_bound_fire() -> None:
    # Strictly-prior mean is 10050; 1000bps below is exactly 9045.
    below = _ticks(9046)
    at = _ticks(9045)
    assert _run(below) == []
    intents = _run(at)
    assert len(intents) == 1
    assert intents[0].mint == "M"


def test_fixture_produces_one_asserted_fill() -> None:
    tape = load_tape(FIXTURE)
    allocation = Allocation(10_000_000, {"mean_reversion": 10_000_000})
    strategy = MeanReversionStrategy({"deviation_bps": 1000})
    intents = StrategyRuntime(tape, {"mean_reversion": strategy}, allocation).run()
    assert len(intents) == 1
    assert intents[0].mint == "RevMint333333333333333333333333333333333"


def test_look_ahead_canary() -> None:
    """The dip tick cannot be anticipated: prefix tapes never fire early."""
    prefix = [
        Tick(ts=1.0, mint="M", price_lamports=10_000),
        Tick(ts=2.0, mint="M", price_lamports=10_100),
        Tick(ts=3.0, mint="M", price_lamports=10_200),
    ]
    assert _run(prefix) == []
    assert len(_run([*prefix, Tick(ts=4.0, mint="M", price_lamports=9000)])) == 1


def test_params_validated_against_bounds() -> None:
    with pytest.raises(ValueError):
        MeanReversionStrategy({"deviation_bps": 10_001})
    with pytest.raises(ValueError):
        MeanReversionStrategy({})
    assert MeanReversionStrategy({"deviation_bps": 0}).BOUNDS == {"deviation_bps": (0, 10000)}
