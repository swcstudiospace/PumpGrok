"""momentum_breakout baseline strategy (STR-04).

Entries on momentum breakout past the declared threshold: a mint whose
price has risen at least ``breakout_bps`` above its lowest price so far
fires one buy. The threshold is a ParamSet parameter, never a literal;
construction validates it against the declared BOUNDS (which equal the
[strategy.momentum_breakout.breakout_bps] TOML section exactly). State
is incremental (on_tick observes only the current tick), so the strategy
cannot read a future tick; the look-ahead canary in tests proves it.
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

__all__ = ["MomentumBreakoutStrategy"]


class MomentumBreakoutStrategy:
    """One-shot momentum-breakout buyer per mint."""

    def __init__(self, params: dict[str, Any]) -> None:
        bounds = bounds_for("momentum_breakout")
        if "breakout_bps" not in params:
            raise ValueError("momentum_breakout requires breakout_bps")
        value = params["breakout_bps"]
        low, high = bounds["breakout_bps"]
        if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
            raise ValueError(f"breakout_bps {value!r} outside [{low}, {high}]")
        self._threshold_bps = value
        self._lows: dict[str, int] = {}
        self._fired: set[str] = set()

    @property
    def id(self) -> str:
        return "momentum_breakout"

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]:
        return bounds_for(self.id)

    def version_id(self, params: dict[str, Any]) -> str:
        return strategy_version_id(self.id, params, code=code_digest(self.id))

    def on_tick(self, tick: Tick) -> None:
        current = self._lows.get(tick.mint)
        if current is None or tick.price_lamports < current:
            self._lows[tick.mint] = tick.price_lamports

    def decide(self, context: StrategyContext) -> Intent | None:
        if isinstance(context, StrategyContext) and context.tape:
            last = context.tape[-1]
            return self._maybe_fire(last)
        return None

    def _maybe_fire(self, tick: Tick) -> Intent | None:
        if tick.mint in self._fired:
            return None
        low = self._lows.get(tick.mint)
        if low is None or low <= 0:
            return None
        move_bps = (tick.price_lamports - low) * 10_000 // low
        if move_bps < self._threshold_bps:
            return None
        self._fired.add(tick.mint)
        return Intent(
            strategy_id=self.id,
            side="buy",
            mint=tick.mint,
            size_lamports=1_000_000,
            reason=f"breakout {move_bps}bps >= {self._threshold_bps}bps",
        )
