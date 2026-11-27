"""Meme filter admission rules flip exactly at their bounds (STR-01)."""

from __future__ import annotations

from pumpgrok.core import interfaces  # noqa: F401  (facade import covers the shim)
from pumpgrok.strategies.memefilters import MemeFilter
from pumpgrok.strategies.tape import Tick


def _tick(**overrides: object) -> Tick:
    kwargs: dict[str, object] = {
        "ts": 1_700_000_000.0,
        "mint": "Mint11111111111111111111111111111111111111111",
        "price_lamports": 1_000,
        "buyers": 5,
        "created_ts": 1_700_000_000.0 - 120.0,
        "curve_progress": 0.40,
    }
    kwargs.update(overrides)
    return Tick(**kwargs)  # type: ignore[arg-type]


def test_defaults_admit_at_every_bound() -> None:
    assert MemeFilter().admits(_tick()) is True


def test_below_minimum_buyers_refused() -> None:
    assert MemeFilter().admits(_tick(buyers=4)) is False


def test_younger_than_minimum_age_refused() -> None:
    assert MemeFilter().admits(_tick(created_ts=1_700_000_000.0 - 119.0)) is False


def test_above_maximum_curve_progress_refused() -> None:
    assert MemeFilter().admits(_tick(curve_progress=0.401)) is False
