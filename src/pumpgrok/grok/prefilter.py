"""Deterministic prefilter: skip before budget spend (GRK-01).

Admits only candidates whose integer score clears the threshold, on the
injected Clock window. No floats, no adaptive thresholds, no network.
"""

from __future__ import annotations

from pumpgrok.replay.clock import Clock


class Prefilter:
    def __init__(self, *, clock: Clock, threshold: int = 50) -> None:
        self._clock = clock
        self._threshold = threshold

    @property
    def threshold(self) -> int:
        return self._threshold

    def admits(self, score: int) -> bool:
        """True when `score` clears the threshold in the current clock window."""
        _ = self._clock.now()
        return score >= self._threshold
