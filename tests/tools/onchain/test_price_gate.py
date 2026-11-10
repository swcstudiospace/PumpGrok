"""Entry price admission must fail closed for untrusted source labels."""

from __future__ import annotations

import pytest

from pumpgrok.tools.onchain import curve_layout


def test_unknown_source_is_rejected() -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source="unknown_live_feed") is False


@pytest.mark.parametrize("source", ["solana_rpc", "rpc:verified", "RPC"])
def test_forged_live_source_is_rejected(source: str) -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source=source) is False


@pytest.mark.parametrize("source", ["rest", "pumpportal"])
def test_unverified_live_source_is_rejected(source: str) -> None:
    assert curve_layout.rpc_curve_price_allowed(curve_source=source) is False


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
