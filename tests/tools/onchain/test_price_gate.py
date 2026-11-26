"""Allowlist price gate (MKT-04): unknown/unverified refused, replay allowed.

Entry price admission must fail closed for untrusted source labels.
"""

from __future__ import annotations

import pytest

from pumpgrok.tools.onchain import curve_layout
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


def test_unknown_source_is_rejected() -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source="unknown_live_feed") is False


@pytest.mark.parametrize("source", ["solana_rpc", "rpc:verified", "RPC"])
def test_forged_live_source_is_rejected(source: str) -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source=source) is False


@pytest.mark.parametrize("source", ["rest", "pumpportal"])
def test_unverified_live_source_is_rejected(source: str) -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source=source) is True


def test_unknown_source_is_rejected_even_with_verified_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert curve_layout.rpc_curve_price_allowed(curve_source="unknown_live_feed") is False


def test_unverified_rpc_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert curve_layout.rpc_curve_price_allowed(curve_source="rpc") is False


def test_verified_rpc_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert curve_layout.rpc_curve_price_allowed(curve_source="rpc") is True


def test_trusted_fixture_replay_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert curve_layout.rpc_curve_price_allowed(curve_source="fixture") is True
