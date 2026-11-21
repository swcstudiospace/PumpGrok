"""STR-01: the registry holds exactly the four D-01 ids and refuses others."""

from __future__ import annotations

import pytest

from pumpgrok.strategies.registry import (
    STRATEGY_IDS,
    get_strategy_bounds,
    is_known_strategy,
    registered_ids,
)


def test_exactly_four_ids() -> None:
    assert registered_ids() == (
        "legacy_screening",
        "momentum_breakout",
        "new_launch_sniper",
        "mean_reversion",
    )
    assert STRATEGY_IDS == registered_ids()
    assert len(set(STRATEGY_IDS)) == 4


def test_unknown_id_refused() -> None:
    assert not is_known_strategy("no_such_strategy")
    with pytest.raises(ValueError):
        get_strategy_bounds("no_such_strategy")


def test_bounds_surface() -> None:
    assert get_strategy_bounds("legacy_screening") == {}
    assert get_strategy_bounds("momentum_breakout") == {"breakout_bps": (0, 10000)}
    assert get_strategy_bounds("new_launch_sniper") == {"max_age_seconds": (0, 86400)}
    assert get_strategy_bounds("mean_reversion") == {"deviation_bps": (0, 10000)}
