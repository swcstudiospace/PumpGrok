"""Meme filter rules for strategy ticks (STR-01).

A :class:`MemeFilter` is the admission gate a strategy consults before
acting on a tick: minimum unique buyers, minimum mint age, and maximum
curve progress. Thresholds default to the desk filter defaults, flip
exactly at their bound (admit means >= minimum and <= maximum), and carry
no LLM, network, or ledger access.
"""

from __future__ import annotations

from dataclasses import dataclass

from pumpgrok.strategies.tape import Tick

__all__ = ["MemeFilter"]


@dataclass(frozen=True)
class MemeFilter:
    """Admission thresholds over a tick (inclusive bounds)."""

    min_unique_buyers: int = 5
    min_age_seconds: float = 120.0
    max_curve_progress: float = 0.40

    def admits(self, tick: Tick) -> bool:
        """Whether a tick passes every rule (each rule flips at its bound)."""
        if tick.buyers < self.min_unique_buyers:
            return False
        if tick.age_seconds < self.min_age_seconds:
            return False
        if tick.curve_progress > self.max_curve_progress:
            return False
        return True
