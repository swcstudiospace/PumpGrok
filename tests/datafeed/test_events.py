"""Datafeed events: integer-only tick fields; float money rejected."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pumpgrok.datafeed.events import CurveTick, GapEvent

GOOD = {
    "mint": "m1",
    "ts_utc": "2026-11-21T00:00:00.000000Z",
    "virtual_sol_reserves_lamports": 42_000_000_000,
    "virtual_token_reserves_units": 766_428_571,
    "real_sol_reserves_lamports": 12_000_000_000,
    "real_token_reserves_units": 500_000_000_000,
    "total_supply_units": 1_000_000_000_000,
    "complete": False,
}


def test_tick_integer_fields() -> None:
    tick = CurveTick.model_validate(GOOD)
    assert tick.virtual_sol_reserves_lamports == 42_000_000_000
    assert isinstance(tick.virtual_sol_reserves_lamports, int)


def test_float_money_rejected() -> None:
    bad = dict(GOOD, virtual_sol_reserves_lamports=4.2e10)
    with pytest.raises(ValidationError):
        CurveTick.model_validate(bad)


def test_extra_forbidden() -> None:
    bad = dict(GOOD, price=1.5)
    with pytest.raises(ValidationError):
        CurveTick.model_validate(bad)


def test_gap_event_fields() -> None:
    gap = GapEvent.model_validate(
        {
            "mint": "m1",
            "ts_utc": "2026-11-21T00:00:30.000000Z",
            "reason": "timeout",
            "from_ts_utc": "2026-11-21T00:00:00.000000Z",
            "to_ts_utc": "2026-11-21T00:00:30.000000Z",
        }
    )
    assert gap.reason == "timeout"
