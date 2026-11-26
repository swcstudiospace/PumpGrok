"""STR-06: strategy parameter overrides are hashed and validated.

A ParamSet carrying strategy overrides must hash differently from the same
set without them (one edit flips the identity), validate through
CandidateParams (scoring knobs and non-scalar leaves refused), and respect
the [strategy.<ID>.<PARAM>] bounds: in-range passes, out-of-range and
unknown ids/params fail with OutOfBoundsError instead of a silent pass.
"""

from __future__ import annotations

import pytest
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
