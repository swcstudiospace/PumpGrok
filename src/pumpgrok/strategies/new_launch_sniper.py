"""new_launch_sniper baseline strategy (STR-04).

Entries bounded to the early window: a mint fires one buy while its age
is at most ``max_age_seconds`` after creation. The window is a ParamSet
parameter, never a literal; construction validates it against the
declared BOUNDS (which equal the [strategy.new_launch_sniper.max_age_seconds]
TOML section exactly). Older mints never fire; state is incremental, so
the look-ahead canary holds.
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

__all__ = ["NewLaunchSniperStrategy"]


class NewLaunchSniperStrategy:
    """One-shot early-window buyer per mint."""

    def __init__(self, params: dict[str, Any]) -> None:
        bounds = bounds_for("new_launch_sniper")
        if "max_age_seconds" not in params:
            raise ValueError("new_launch_sniper requires max_age_seconds")
        value = params["max_age_seconds"]
        low, high = bounds["max_age_seconds"]
        if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
            raise ValueError(f"max_age_seconds {value!r} outside [{low}, {high}]")
        self._max_age = value
        self._fired: set[str] = set()

    @property
    def id(self) -> str:
        return "new_launch_sniper"

    @property
    def BOUNDS(self) -> dict[str, tuple[int, int]]:
        return bounds_for(self.id)

    def version_id(self, params: dict[str, Any]) -> str:
        return strategy_version_id(self.id, params, code=code_digest(self.id))

    def on_tick(self, tick: Tick) -> None:
        return None

    def decide(self, context: StrategyContext) -> Intent | None:
        if not context.tape:
            return None
        tick = context.tape[-1]
        if tick.mint in self._fired:
            return None
        if tick.created_ts is None or tick.age_seconds > self._max_age:
            return None
        self._fired.add(tick.mint)
        return Intent(
            strategy_id=self.id,
            side="buy",
            mint=tick.mint,
            size_lamports=1_000_000,
            reason=f"early window age {tick.age_seconds}s <= {self._max_age}s",
        )
