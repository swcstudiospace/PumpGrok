"""Static, ordered strategy registry (STR-01).

The registry is a literal tuple of strategy classes in a fixed order. There is no
dynamic loading and no entry-point discovery. checked_registry runs at import and
refuses a duplicate strategy_id, so a clash stops the process before any strategy runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from pumpgrok.strategies.base import Intent, Strategy, StrategyContext
from pumpgrok.upgrade.bounds import KeyBound

__all__ = [
    "STRATEGIES",
    "LegacyScreening",
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


class LegacyScreening:
    """The legacy screening strategy. It declares no tunable parameters, so no bounds.

    Its decisions come from the existing replay decision path, which the runtime wires
    in 15-03. This hook declares no intents of its own.
    """

    strategy_id: ClassVar[str] = "legacy_screening"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        return ()


STRATEGIES: tuple[type[Strategy], ...] = checked_registry(LegacyScreening)
