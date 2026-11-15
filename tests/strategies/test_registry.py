"""STR-01: the strategy registry is static, ordered, and refuses duplicate ids.

BOUNDS declared on each registered strategy must equal its [strategy.ID.*] tables in
upgrade_bounds.toml exactly. The three baseline strategies are not written until 15-04;
their TOML tables are named in DEFERRED_TO_15_04 and checked for presence and absence
here, so no equality assertion is skipped and none is silently dropped.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pytest

from pumpgrok.strategies import Intent, StrategyContext, TapePoint, TickSnapshot
from pumpgrok.strategies.registry import (
    STRATEGIES,
    LegacyScreening,
    StrategyRegistryError,
    checked_registry,
)
from pumpgrok.upgrade.bounds import KeyBound, default_bounds_path, load_bounds

DEFERRED_TO_15_04 = frozenset({"momentum_breakout", "new_launch_sniper", "mean_reversion"})


def _toml_sections() -> dict[str, dict[str, KeyBound]]:
    return load_bounds(default_bounds_path()).strategy


class _Alpha:
    strategy_id: ClassVar[str] = "alpha"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        return ()


class _AlphaTwin:
    strategy_id: ClassVar[str] = "alpha"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        return ()


class _Beta:
    strategy_id: ClassVar[str] = "beta"
    BOUNDS: ClassVar[Mapping[str, KeyBound]] = {}
    DEFAULTS: ClassVar[Mapping[str, Any]] = {}

    def on_tick(self, context: StrategyContext) -> tuple[Intent, ...]:
        return ()


def test_registry_is_a_static_ordered_tuple() -> None:
    assert isinstance(STRATEGIES, tuple)
    assert [cls.strategy_id for cls in STRATEGIES] == ["legacy_screening"]


def test_checked_registry_keeps_the_given_order() -> None:
    built = checked_registry(_Beta, _Alpha)
    assert [cls.strategy_id for cls in built] == ["beta", "alpha"]


def test_duplicate_strategy_id_is_refused() -> None:
    with pytest.raises(StrategyRegistryError, match="alpha"):
        checked_registry(_Alpha, _AlphaTwin)


def test_legacy_screening_is_registered_with_empty_bounds() -> None:
    assert LegacyScreening.strategy_id == "legacy_screening"
    assert dict(LegacyScreening.BOUNDS) == {}
    assert LegacyScreening in STRATEGIES


def test_legacy_screening_has_no_toml_section() -> None:
    assert "legacy_screening" not in _toml_sections()


def test_registered_bounds_equal_toml_sections_exactly() -> None:
    sections = _toml_sections()
    for cls in STRATEGIES:
        declared = dict(cls.BOUNDS)
        toml_keys = sections.get(cls.strategy_id, {})
        assert declared == toml_keys, cls.strategy_id


def test_toml_sections_not_registered_are_exactly_the_deferred_three() -> None:
    registered = {cls.strategy_id for cls in STRATEGIES}
    unregistered_in_toml = set(_toml_sections()) - registered
    assert unregistered_in_toml == DEFERRED_TO_15_04


def test_legacy_hook_declares_no_intents() -> None:
    ctx = StrategyContext(
        now=1.0,
        version_id="v",
        tick=TickSnapshot(
            mint="MintA",
            ts=1.0,
            launch_ts=0.0,
            price_lamports=1,
            unique_buyers=1,
            curve_progress=0.0,
        ),
        tape=(TapePoint(ts=1.0, price_lamports=1),),
    )
    assert LegacyScreening().on_tick(ctx) == ()
