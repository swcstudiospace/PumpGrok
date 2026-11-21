"""Fallback ladder with breaker and half-open probe (GRK-06, T-14-02-02/03).

Keyed by `signal_scoring_mode`: primary model, then the fast model, then a
deterministic fallback. The breaker opens on repeated failure; a half-open
probe re-admits the primary after a cooldown on the injected Clock. Fallback
results are never cached (enforced by the 14-01 cache).
"""

from __future__ import annotations

from pumpgrok.replay.clock import Clock

_MODES = ("primary", "fast", "deterministic")


class FallbackLadder:
    def __init__(
        self,
        *,
        clock: Clock,
        signal_scoring_mode: str = "primary",
        failure_threshold: int = 3,
        cooldown_s: float = 60.0,
    ) -> None:
        if signal_scoring_mode not in _MODES:
            raise ValueError(f"unknown signal_scoring_mode: {signal_scoring_mode}")
        self._clock = clock
        self._mode = signal_scoring_mode
        self._threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def breaker_open(self) -> bool:
        if self._opened_at is None:
            return False
        return self._clock.now() - self._opened_at < self._cooldown_s

    def next_model(self, primary: str, fast: str) -> str:
        """The model to try now, honoring the breaker."""
        if self.breaker_open:
            return "deterministic"
        if self._mode == "fast":
            return fast
        if self._mode == "deterministic":
            return "deterministic"
        return primary

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold and self._opened_at is None:
            self._opened_at = self._clock.now()

    def record_success(self) -> None:
        was_probe = self._opened_at is not None and not self.breaker_open
        if was_probe:
            self._failures = 0
            self._opened_at = None
        elif self._opened_at is None:
            self._failures = 0

    def try_half_open_probe(self) -> bool:
        """Single-flight half-open admission after the cooldown elapses."""
        if self._opened_at is None or self.breaker_open:
            return False
        if self._probe_in_flight:
            return False
        self._probe_in_flight = True
        return True

    def finish_probe(self, *, success: bool) -> None:
        self._probe_in_flight = False
        if success:
            self._failures = 0
            self._opened_at = None
        else:
            self._opened_at = self._clock.now()

    def deterministic_result(self, consequence_id: str) -> str:
        """Deterministic fallback payload (integer money only, no network)."""
        total = sum(ord(c) for c in consequence_id) % 100
        return '{"score": %d, "source": "deterministic"}' % total
