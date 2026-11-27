"""S-B4 (PRM-02): upgrade bounds refuse non-finite values and non-finite bounds.

NaN compares False against every bound, so an unchecked NaN passes both the
ordering check that loads a bound and the range check that admits an override.
Infinite overrides already fail the range check; they are covered here so the
finite rule stays pinned for both directions.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from pumpgrok.upgrade.bounds import OutOfBoundsError, default_bounds_path, load_bounds
from pumpgrok.upgrade.bounds import validate_against_bounds as validate
from pumpgrok.upgrade.params import ParamSet

_KEY = "max_curve_progress"
_MIN_LINE = f"[filter.{_KEY}]\nmin = 0.0\n"
_MAX_LINE = f"[filter.{_KEY}]\nmin = 0.0\nmax = 1.0\n"


def _bounds_with(tmp_path: Path, old: str, new: str) -> Path:
    text = default_bounds_path().read_text(encoding="utf-8")
    assert text.count(old) == 1, "fixture anchor must name exactly one bound entry"
    path = tmp_path / "upgrade_bounds.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


def _override(value: float) -> ParamSet:
    # model_construct skips CandidateParams validation so the bounds check alone sees the value.
    return ParamSet.model_construct(filter={_KEY: value}, exits={}, strategy=None)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_override_is_refused(value: float) -> None:
    with pytest.raises(OutOfBoundsError):
        validate(_override(value), load_bounds())


def test_nan_min_bound_refuses_to_load(tmp_path: Path) -> None:
    path = _bounds_with(tmp_path, _MIN_LINE, f"[filter.{_KEY}]\nmin = nan\n")
    with pytest.raises(ValueError, match="finite"):
        load_bounds(path)


def test_nan_max_bound_refuses_to_load(tmp_path: Path) -> None:
    path = _bounds_with(tmp_path, _MAX_LINE, f"[filter.{_KEY}]\nmin = 0.0\nmax = nan\n")
    with pytest.raises(ValueError, match="finite"):
        load_bounds(path)


def test_infinite_bound_refuses_to_load(tmp_path: Path) -> None:
    path = _bounds_with(tmp_path, _MAX_LINE, f"[filter.{_KEY}]\nmin = 0.0\nmax = inf\n")
    with pytest.raises(ValueError, match="finite"):
        load_bounds(path)


def test_finite_values_inside_bounds_still_pass() -> None:
    validate(_override(0.5), load_bounds())
