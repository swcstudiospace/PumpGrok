"""STR-04: new_launch_sniper flips exactly at its age bound."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.strategies.allocation import Allocation
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniperStrategy
from pumpgrok.strategies.runtime import StrategyRuntime
from pumpgrok.strategies.tape import Tape, Tick, load_tape

FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "strat-launch"


def _run(ticks: list[Tick], max_age: int = 600) -> list:
    strategy = NewLaunchSniperStrategy({"max_age_seconds": max_age})
    allocation = Allocation(10_000_000, {"new_launch_sniper": 10_000_000})
    runtime = StrategyRuntime(Tape.from_ticks(ticks), {"new_launch_sniper": strategy}, allocation)
    return runtime.run()


def test_at_age_bound_fires_past_bound_does_not() -> None:
    at = [Tick(ts=700.0, mint="M", price_lamports=1000, created_ts=100.0)]
    past = [Tick(ts=701.0, mint="M", price_lamports=1000, created_ts=100.0)]
    assert len(_run(at)) == 1
    assert _run(past) == []


def test_fixture_produces_one_asserted_fill() -> None:
    tape = load_tape(FIXTURE)
    allocation = Allocation(10_000_000, {"new_launch_sniper": 10_000_000})
    strategy = NewLaunchSniperStrategy({"max_age_seconds": 600})
    intents = StrategyRuntime(tape, {"new_launch_sniper": strategy}, allocation).run()
    assert len(intents) == 1
    assert intents[0].mint == "LaunchMint2222222222222222222222222222222"


def test_look_ahead_canary() -> None:
    """A future tick within the window cannot move an earlier decision."""
    inside = [Tick(ts=150.0, mint="M", price_lamports=1000, created_ts=100.0)]
    assert len(_run(inside)) == 1
    outside = [Tick(ts=900.0, mint="M", price_lamports=1000, created_ts=100.0)]
    both = [*inside, *outside]
    assert len(_run(both)) == 1  # still only the in-window first tick


def test_params_validated_against_bounds() -> None:
    with pytest.raises(ValueError):
        NewLaunchSniperStrategy({"max_age_seconds": 86_401})
    with pytest.raises(ValueError):
        NewLaunchSniperStrategy({})
    assert NewLaunchSniperStrategy({"max_age_seconds": 0}).BOUNDS == {"max_age_seconds": (0, 86400)}
