"""Liquidity depth is decided on the exact lamport ratio, not a float division (TOOL-003)."""

from __future__ import annotations

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.tools.safety.checks.readers import check_liquidity_depth


def test_depth_just_below_floor_fails_even_beyond_float_precision() -> None:
    # The exact ratio is 2 - 2**-60, under the 2.0 floor; float division rounds it to 2.0.
    thresholds = SafetyThresholds(liquidity_multiple_min=2.0, liquidity_multiple_recommended=5.0)
    result = check_liquidity_depth({"liquidity_lamports": 2**61 - 1}, 2**60, thresholds)
    assert result.status == "fail"


def test_depth_exactly_at_floor_is_not_a_failure() -> None:
    thresholds = SafetyThresholds(liquidity_multiple_min=2.0, liquidity_multiple_recommended=5.0)
    result = check_liquidity_depth({"liquidity_lamports": 2 * 10**9}, 10**9, thresholds)
    assert result.status == "warn"
