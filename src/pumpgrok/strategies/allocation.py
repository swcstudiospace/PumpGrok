"""Integer capital slices per strategy (STR-03).

A slice is equity_lamports * fraction_bps // 10000, floor-divided. The fractions are basis
points, so no value here is a float. Because each slice is floored and the fractions total at
most 10000 bps, the slices sum to at most the equity. Exposure enforcement at the engine is a
later phase (RSK-01); this module only computes the slices.
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = ["BPS_FULL", "AllocationError", "slice_lamports"]

BPS_FULL = 10_000


class AllocationError(ValueError):
    """An allocation input is not an integer, is negative, or over-allocates the equity."""


def _as_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AllocationError(f"{name} must be an int")
    return value


def slice_lamports(equity_lamports: int, fractions_bps: Mapping[str, int]) -> dict[str, int]:
    """Each strategy's integer lamport slice of the equity, from its basis-point fraction."""
    equity = _as_int(equity_lamports, "equity_lamports")
    if equity < 0:
        raise AllocationError("equity_lamports must not be negative")
    total = 0
    for name, bps in fractions_bps.items():
        value = _as_int(bps, f"fraction for {name}")
        if value < 0:
            raise AllocationError(f"fraction for {name} must not be negative")
        total += value
    if total > BPS_FULL:
        raise AllocationError(f"fractions total {total} bps, above the {BPS_FULL} bps ceiling")
    return {name: equity * int(bps) // BPS_FULL for name, bps in fractions_bps.items()}
