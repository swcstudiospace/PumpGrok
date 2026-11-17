"""Static, ordered strategy registry (STR-01).

The registry is a literal tuple of strategy classes in a fixed order. There is no
dynamic loading and no entry-point discovery. checked_registry runs at import and
refuses a duplicate strategy_id, so a clash stops the process before any strategy runs.
LegacyScreening lives in strategies.legacy (the adapter over the replay decision path).
The three baseline strategies (15-04) are listed after it, so the registry names every
registered strategy.
"""

from __future__ import annotations

from pumpgrok.strategies.base import Strategy
from pumpgrok.strategies.legacy import LegacyScreening
from pumpgrok.strategies.mean_reversion import MeanReversion
from pumpgrok.strategies.momentum_breakout import MomentumBreakout
from pumpgrok.strategies.new_launch_sniper import NewLaunchSniper

__all__ = [
    "STRATEGIES",
    "LegacyScreening",
    "MeanReversion",
    "MomentumBreakout",
    "NewLaunchSniper",
    "StrategyRegistryError",
    "checked_registry",
]


class StrategyRegistryError(ValueError):
    """The registry is malformed: a duplicate or empty strategy id."""


def checked_registry(*classes: type[Strategy]) -> tuple[type[Strategy], ...]:
    """Return the classes in the given order, refusing duplicate or empty ids."""
    seen: set[str] = set()
    for cls in classes:
        strategy_id = cls.strategy_id
        if not strategy_id:
            raise StrategyRegistryError(f"strategy {cls.__name__} has an empty strategy_id")
        if strategy_id in seen:
            raise StrategyRegistryError(f"duplicate strategy_id in registry: {strategy_id}")
        seen.add(strategy_id)
    return tuple(classes)


STRATEGIES: tuple[type[Strategy], ...] = checked_registry(
    LegacyScreening,
    MomentumBreakout,
    NewLaunchSniper,
    MeanReversion,
)
