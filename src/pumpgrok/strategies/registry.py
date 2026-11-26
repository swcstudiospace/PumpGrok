<<<<<<< HEAD
"""Static strategy registry (STR-01, D-01).

The registry holds exactly the four D-01 ids and refuses unknown ids: an
unregistered strategy cannot be instantiated through this surface. The
mapping is static by design (a class registry, never a plugin loader), so
adding a fifth strategy is a code change visible in review.
=======
"""Static, ordered strategy registry (STR-01).

The registry is a literal tuple of strategy classes in a fixed order. There is no
dynamic loading and no entry-point discovery. checked_registry runs at import and
refuses a duplicate strategy_id, so a clash stops the process before any strategy runs.
LegacyScreening lives in strategies.legacy (the adapter over the replay decision path).
The three baseline strategies (15-04) are listed after it, so the registry names every
registered strategy.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
import importlib
from collections.abc import Callable
from typing import Any, cast

from pumpgrok.strategies.base import STRATEGY_IDS, bounds_for

__all__ = ["STRATEGY_IDS", "get_strategy_bounds", "is_known_strategy", "registered_ids"]


def registered_ids() -> tuple[str, str, str, str]:
    """The four registered ids in declaration order."""
    return STRATEGY_IDS


def is_known_strategy(strategy_id: str) -> bool:
    """Whether an id is one of the four registered strategies."""
    return strategy_id in STRATEGY_IDS


def get_strategy_bounds(strategy_id: str) -> dict[str, tuple[int, int]]:
    """Declared BOUNDS for a registered id; refuses unknown ids."""
    if strategy_id not in STRATEGY_IDS:
        raise ValueError(f"unknown strategy id: {strategy_id!r}")
    return bounds_for(strategy_id)


def resolve_factory(strategy_id: str) -> Callable[..., Any]:
    """Import and return the concrete strategy class for an id (never silent)."""

    if strategy_id not in STRATEGY_IDS:
        raise ValueError(f"unknown strategy id: {strategy_id!r}")
    module_name = (
        "pumpgrok.strategies.legacy"
        if strategy_id == "legacy_screening"
        else {
            "momentum_breakout": "pumpgrok.strategies.momentum_breakout",
            "new_launch_sniper": "pumpgrok.strategies.new_launch_sniper",
            "mean_reversion": "pumpgrok.strategies.mean_reversion",
        }[strategy_id]
    )
    module = importlib.import_module(module_name)
    cls_name = {
        "legacy_screening": "LegacyScreeningStrategy",
        "momentum_breakout": "MomentumBreakoutStrategy",
        "new_launch_sniper": "NewLaunchSniperStrategy",
        "mean_reversion": "MeanReversionStrategy",
    }[strategy_id]
    factory = getattr(module, cls_name, None)
    if factory is None:
        factory = module
    return cast(Callable[..., Any], factory)
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
