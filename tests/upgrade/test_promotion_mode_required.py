"""S-P1: run_promotion_check has no default mode, so no call promotes without choosing one.

Unfixed code: cli/promotion.py:237 is ``automatic: bool = False``. The signature test fails on
that default, and the call without a mode runs the human path instead of raising TypeError.
The invalid-mode test targets the same parameter: unfixed code has no ``mode`` keyword at all.
"""

from __future__ import annotations

import inspect

import pytest

from pumpgrok.cli import promotion


def _check(**overrides: object) -> object:
    """One check with every required argument but mode; space is empty, so no path does work."""
    kwargs: dict[str, object] = {
        "clock": None,
        "space": [],
        "seed": 0,
        "initial_equity_lamports": 0,
    }
    kwargs.update(overrides)
    checker = promotion.run_promotion_check
    return checker(None, "no-such-dataset", **kwargs)  # type: ignore[arg-type]


def test_mode_is_a_required_keyword_with_no_default() -> None:
    param = inspect.signature(promotion.run_promotion_check).parameters["mode"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY


def test_call_without_mode_is_refused() -> None:
    with pytest.raises(TypeError, match="mode"):
        _check()


def test_unknown_mode_is_refused_and_does_not_fall_through_to_human() -> None:
    with pytest.raises(ValueError, match="mode"):
        _check(mode="promote")
