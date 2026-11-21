"""Static strategy registry (STR-01, D-01).

The registry holds exactly the four D-01 ids and refuses unknown ids: an
unregistered strategy cannot be instantiated through this surface. The
mapping is static by design (a class registry, never a plugin loader), so
adding a fifth strategy is a code change visible in review.
"""

from __future__ import annotations

from typing import Any, Callable

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
    import importlib

    if strategy_id not in STRATEGY_IDS:
        raise ValueError(f"unknown strategy id: {strategy_id!r}")
    module_name = "pumpgrok.strategies.legacy" if strategy_id == "legacy_screening" else {
        "momentum_breakout": "pumpgrok.strategies.momentum_breakout",
        "new_launch_sniper": "pumpgrok.strategies.new_launch_sniper",
        "mean_reversion": "pumpgrok.strategies.mean_reversion",
    }[strategy_id]
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
    return factory
