"""EVENT_DECODE_STATUS stays ASSUMED without a human reviewed_by (MKT-10)."""

from __future__ import annotations

from pumpgrok.tools.onchain.curve_layout import LAYOUT_STATUS, rpc_curve_price_allowed
from pumpgrok.tools.onchain.pump_events import (
    EVENT_DECODE_REVIEWED_BY,
    EVENT_DECODE_STATUS,
    decode_status,
)


def test_shipped_literals_assumed() -> None:
    assert EVENT_DECODE_STATUS == "ASSUMED"
    assert EVENT_DECODE_REVIEWED_BY is None
    assert LAYOUT_STATUS == "ASSUMED"


def test_no_reviewer_stays_assumed() -> None:
    assert decode_status(reviewed_by=None) == "ASSUMED"
    assert decode_status(reviewed_by="") == "ASSUMED"
    assert rpc_curve_price_allowed(curve_source="rpc") is False


def test_human_reviewer_flips_only_in_double() -> None:
    assert decode_status(reviewed_by="human:alice 2026-11-21") == "VERIFIED"
    # The shipped literal never follows the double.
    assert EVENT_DECODE_STATUS == "ASSUMED"
