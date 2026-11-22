"""Allowlist price gate (MKT-04): unknown/unverified refused, replay allowed."""

from __future__ import annotations

from pumpgrok.tools.onchain.curve_layout import LAYOUT_STATUS, rpc_curve_price_allowed
from pumpgrok.tools.onchain.pump_events import EVENT_DECODE_STATUS


def test_rpc_refused_while_assumed() -> None:
    assert LAYOUT_STATUS == "ASSUMED"
    assert EVENT_DECODE_STATUS == "ASSUMED"
    assert rpc_curve_price_allowed(curve_source="rpc") is False


def test_replay_and_fixture_allowed() -> None:
    assert rpc_curve_price_allowed(curve_source="replay") is True
    assert rpc_curve_price_allowed(curve_source="fixture") is True


def test_unknown_refused() -> None:
    assert rpc_curve_price_allowed(curve_source="unknown") is False
    assert rpc_curve_price_allowed(curve_source="") is False
