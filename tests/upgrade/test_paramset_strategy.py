<<<<<<< HEAD
"""STR-06: strategy parameter overrides are hashed and validated.

A ParamSet carrying strategy overrides must hash differently from the same
set without them (one edit flips the identity), validate through
CandidateParams (scoring knobs and non-scalar leaves refused), and respect
the [strategy.<ID>.<PARAM>] bounds: in-range passes, out-of-range and
unknown ids/params fail with OutOfBoundsError instead of a silent pass.
=======
"""STR-06: strategy parameter bounds are version-controlled, fail closed, never clamped.

The twelve proposed bounds below are PENDING OWNER APPROVAL (Phase 15 owner
decision 2). They mirror the parameter proposals table in 15-PLANS-INDEX.md.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

import pytest
<<<<<<< HEAD
from pydantic import ValidationError

from pumpgrok.upgrade.bounds import OutOfBoundsError, load_bounds, validate_against_bounds
from pumpgrok.upgrade.params import ParamSet


def test_strategy_params_change_the_hash() -> None:
    base = ParamSet(filter={"min_unique_buyers": 5})
    with_strategy = ParamSet(
        filter={"min_unique_buyers": 5},
        strategy={"momentum_breakout": {"breakout_bps": 100}},
    )
    assert with_strategy.content_hash != base.content_hash
    assert with_strategy.content_hash != ParamSet().content_hash


def test_strategy_param_edit_flips_the_hash() -> None:
    first = ParamSet(strategy={"new_launch_sniper": {"max_age_seconds": 600}})
    second = ParamSet(strategy={"new_launch_sniper": {"max_age_seconds": 601}})
    assert first.content_hash != second.content_hash


def test_strategy_hash_is_order_insensitive() -> None:
    first = ParamSet(
        strategy={
            "momentum_breakout": {"breakout_bps": 100},
            "mean_reversion": {"deviation_bps": 50},
        }
    )
    second = ParamSet(
        strategy={
            "mean_reversion": {"deviation_bps": 50},
            "momentum_breakout": {"breakout_bps": 100},
        }
    )
    assert first.content_hash == second.content_hash


def test_scoring_knobs_and_non_scalar_leaves_refused() -> None:
    with pytest.raises(ValidationError):
        ParamSet(strategy={"momentum_breakout": {"min_total_score": 0.9}})
    with pytest.raises(ValidationError):
        ParamSet(strategy={"momentum_breakout": {"breakout_bps": {"nested": 1}}})
    with pytest.raises(ValidationError):
        ParamSet(strategy={"momentum_breakout": {"breakout_bps": [100]}})


def test_in_range_strategy_value_passes_bounds() -> None:
    params = ParamSet(strategy={"momentum_breakout": {"breakout_bps": 100}})
    validate_against_bounds(params, load_bounds())
    edge = ParamSet(strategy={"momentum_breakout": {"breakout_bps": 10000}})
    validate_against_bounds(edge, load_bounds())


def test_out_of_range_strategy_value_rejected() -> None:
    params = ParamSet(strategy={"momentum_breakout": {"breakout_bps": 99999}})
    with pytest.raises(OutOfBoundsError):
        validate_against_bounds(params, load_bounds())


def test_unknown_strategy_and_param_rejected() -> None:
    with pytest.raises(OutOfBoundsError):
        validate_against_bounds(
            ParamSet(strategy={"no_such_strategy": {"x": 1}}),
            load_bounds(),
        )
    with pytest.raises(OutOfBoundsError):
        validate_against_bounds(
            ParamSet(strategy={"momentum_breakout": {"no_such_param": 1}}),
            load_bounds(),
        )
=======

from pumpgrok.config.settings import ExitsSettings, FilterSettings
from pumpgrok.upgrade.bounds import (
    KeyBound,
    OutOfBoundsError,
    load_bounds,
    validate_against_bounds,
)
from pumpgrok.upgrade.params import ParamSet

PROPOSED_BOUNDS: dict[tuple[str, str], tuple[float, float]] = {
    ("momentum_breakout", "lookback_seconds"): (60, 1800),
    ("momentum_breakout", "breakout_pct"): (1.0, 200.0),
    ("momentum_breakout", "max_hold_seconds"): (60, 3600),
    ("momentum_breakout", "stop_loss_pct"): (1.0, 100.0),
    ("new_launch_sniper", "max_age_seconds"): (10, 900),
    ("new_launch_sniper", "min_unique_buyers"): (1, 1000),
    ("new_launch_sniper", "max_curve_progress"): (0.0, 1.0),
    ("new_launch_sniper", "take_profit_pct"): (1.0, 1000.0),
    ("mean_reversion", "window_seconds"): (60, 7200),
    ("mean_reversion", "z_threshold"): (0.5, 5.0),
    ("mean_reversion", "max_hold_seconds"): (60, 3600),
    ("mean_reversion", "stop_loss_pct"): (1.0, 100.0),
}

PROPOSED_START_VALUES: dict[str, dict[str, float]] = {
    "momentum_breakout": {
        "lookback_seconds": 300,
        "breakout_pct": 20.0,
        "max_hold_seconds": 900,
        "stop_loss_pct": 25.0,
    },
    "new_launch_sniper": {
        "max_age_seconds": 300,
        "min_unique_buyers": 5,
        "max_curve_progress": 0.10,
        "take_profit_pct": 80.0,
    },
    "mean_reversion": {
        "window_seconds": 600,
        "z_threshold": 2.0,
        "max_hold_seconds": 900,
        "stop_loss_pct": 15.0,
    },
}


def test_strategy_bounds_match_the_twelve_proposals() -> None:
    """The shipped strategy table holds exactly the twelve proposed sections."""
    strategy = load_bounds().strategy
    shipped = {
        (strategy_id, key): (bound.minimum, bound.maximum)
        for strategy_id, keys in strategy.items()
        for key, bound in keys.items()
    }
    assert shipped == PROPOSED_BOUNDS
    assert all(isinstance(bound, KeyBound) for keys in strategy.values() for bound in keys.values())


def test_every_strategy_bound_is_ordered() -> None:
    """Every strategy bound has min <= max."""
    for keys in load_bounds().strategy.values():
        for bound in keys.values():
            assert bound.minimum <= bound.maximum


def test_proposed_start_values_are_admitted() -> None:
    """Each proposed start value sits inside its bound and validates."""
    params = ParamSet(strategy=PROPOSED_START_VALUES)
    validate_against_bounds(params, load_bounds())


def test_out_of_bound_strategy_value_is_refused_naming_key_not_value() -> None:
    """An override outside its bound raises OutOfBoundsError naming the key, never the value."""
    params = ParamSet(strategy={"momentum_breakout": {"lookback_seconds": 1801}})
    with pytest.raises(OutOfBoundsError) as excinfo:
        validate_against_bounds(params, load_bounds())
    message = str(excinfo.value)
    assert "momentum_breakout.lookback_seconds" in message
    assert "1801" not in message


def test_out_of_bound_strategy_value_is_not_clamped() -> None:
    """A value below its minimum is refused, not raised to the minimum."""
    params = ParamSet(strategy={"mean_reversion": {"z_threshold": 0.1}})
    with pytest.raises(OutOfBoundsError, match=r"mean_reversion\.z_threshold"):
        validate_against_bounds(params, load_bounds())


def test_strategy_id_without_bound_is_refused() -> None:
    """A strategy id with no version-controlled bound is never accepted silently."""
    params = ParamSet(strategy={"ghost_strategy": {"anything": 1}})
    with pytest.raises(OutOfBoundsError, match="ghost_strategy"):
        validate_against_bounds(params, load_bounds())


def test_strategy_key_without_bound_is_refused() -> None:
    """A parameter key inside a bounded strategy with no bound is refused."""
    params = ParamSet(strategy={"momentum_breakout": {"unbounded_knob": 1}})
    with pytest.raises(OutOfBoundsError, match=r"momentum_breakout\.unbounded_knob"):
        validate_against_bounds(params, load_bounds())


def test_filter_and_exits_bounds_are_unchanged() -> None:
    """The strategy sections do not alter the filter and exits tables."""
    bounds = load_bounds()
    assert set(bounds.filter) == set(FilterSettings.model_fields) - {"min_total_score"}
    assert set(bounds.exits) == set(ExitsSettings.model_fields)
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
