"""mean_reversion baseline strategy (STR-04).

Entries on reversion from the declared deviation: when a mint's price
sits at least ``deviation_bps`` below the mean of its prior prices, one
buy fires. Debugging matters: "mean" is the strictly-prior price mean,
so the current tick never pulls its own reference and a future tick can
never move an earlier decision (the look-ahead canary holds). The
deviation is a ParamSet parameter, never a literal; construction
validates it against the declared BOUNDS (which equal the
[strategy.mean_reversion.deviation_bps] TOML section exactly).
"""

from __future__ import annotations

from typing import Any

from pumpgrok.strategies.base import (
    Intent,
    StrategyContext,
    bounds_for,
    code_digest,
    strategy_version_id,
)
from pumpgrok.strategies.tape import Tick

__all__ = ["MeanReversionStrategy"]


class MeanReversionStrategy:
    """One-shot dip-buyer per mint."""

    def __init__(self, params: dict[str, Any]) -> None:
        bounds = bounds_for("mean_reversion")
        if "deviation_bps" not in params:
            raise ValueError("mean_reversion requires deviation_bps")
        value = params["deviation_bps"]
        low, high = bounds["deviation_bps"]
        if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
            raise ValueError(f"deviation_bps {value!r} outside [{low}, {high}]")
        self._threshold_bps = value
        self._history: dict[str, list[int]] = {}
        self._fired: set[str] = set()

    @property
    def id(self) -> str:
        return "mean_reversion"

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]:
        return bounds_for(self.id)

    def version_id(self, params: dict[str, Any]) -> str:
        return strategy_version_id(self.id, params, code=code_digest(self.id))

    def on_tick(self, tick: Tick) -> None:
        self._history.setdefault(tick.mint, []).append(tick.price_lamports)

    def decide(self, context: StrategyContext) -> Intent | None:
        if not context.tape:
            return None
        tick = context.tape[-1]
        if tick.mint in self._fired:
            return None
        history = self._history.get(tick.mint, [])
        # Strictly prior prices only: history holds every observed tick
        # including the current one, so the reference excludes the last.
        prior = history[:-1] if len(history) > 1 else history
        if len(prior) < 2:
            return None
        mean = sum(prior) // len(prior)
        if mean <= 0:
            return None
        deviation_bps = (mean - tick.price_lamports) * 10_000 // mean
        if deviation_bps < self._threshold_bps:
            return None
        self._fired.add(tick.mint)
        return Intent(
            strategy_id=self.id,
            side="buy",
            mint=tick.mint,
            size_lamports=1_000_000,
            reason=f"reversion {deviation_bps}bps >= {self._threshold_bps}bps",
        )
