"""Fallback ladder follows signal_scoring_mode; breaker and probe on FixtureClock."""

from pumpgrok.grok.fallback import FallbackLadder
from pumpgrok.replay.clock import FixtureClock


def test_primary_mode_picks_primary() -> None:
    ladder = FallbackLadder(clock=FixtureClock(), signal_scoring_mode="primary")
    assert ladder.next_model("strong", "fast") == "strong"


def test_fast_mode_picks_fast() -> None:
    ladder = FallbackLadder(clock=FixtureClock(), signal_scoring_mode="fast")
    assert ladder.next_model("strong", "fast") == "fast"


def test_breaker_opens_and_probe_readmits() -> None:
    clock = FixtureClock()
    ladder = FallbackLadder(clock=clock, signal_scoring_mode="primary")
    for _ in range(3):
        ladder.record_failure()
    assert ladder.breaker_open
    assert ladder.next_model("strong", "fast") == "deterministic"
    clock.advance_to(61.0)
    assert not ladder.breaker_open
    assert ladder.try_half_open_probe()
    assert not ladder.try_half_open_probe()
    ladder.finish_probe(success=True)
    assert not ladder.breaker_open
    assert ladder.next_model("strong", "fast") == "strong"


def test_probe_failure_reopens_breaker() -> None:
    clock = FixtureClock()
    ladder = FallbackLadder(clock=clock, signal_scoring_mode="primary")
    for _ in range(3):
        ladder.record_failure()
    clock.advance_to(61.0)
    assert ladder.try_half_open_probe()
    ladder.finish_probe(success=False)
    assert ladder.breaker_open


def test_deterministic_result_is_stable() -> None:
    ladder = FallbackLadder(clock=FixtureClock())
    assert ladder.deterministic_result("ev-1") == ladder.deterministic_result("ev-1")
