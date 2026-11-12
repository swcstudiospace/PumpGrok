"""Entry price admission must fail closed unless provenance is verified replay."""

from __future__ import annotations

import pytest

from pumpgrok.tools.onchain import curve_layout
from pumpgrok.tools.onchain.curve_layout import CurveProvenance, rpc_curve_price_allowed

NON_REPLAY_PROVENANCES = [
    CurveProvenance.UNVERIFIED_FIXTURE,
    CurveProvenance.LIVE_RPC,
    CurveProvenance.UNKNOWN,
]


@pytest.mark.parametrize("provenance", NON_REPLAY_PROVENANCES)
def test_non_replay_snapshot_labelled_fixture_is_refused(provenance: CurveProvenance) -> None:
    assert rpc_curve_price_allowed(curve_source="fixture", provenance=provenance) is False


def test_verified_replay_provenance_is_admitted() -> None:
    assert (
        rpc_curve_price_allowed(
            curve_source="fixture", provenance=CurveProvenance.VERIFIED_REPLAY
        )
        is True
    )


@pytest.mark.parametrize(
    "source", ["unknown_live_feed", "solana_rpc", "rpc:verified", "RPC", "rpc", "rest", "pumpportal"]
)
def test_unknown_source_is_refused_even_with_verified_replay(source: str) -> None:
    assert (
        rpc_curve_price_allowed(curve_source=source, provenance=CurveProvenance.VERIFIED_REPLAY)
        is False
    )


@pytest.mark.parametrize("source", ["unknown_live_feed", "rpc", "rest", "pumpportal", "fixture"])
def test_unknown_provenance_is_refused_for_any_source(source: str) -> None:
    assert rpc_curve_price_allowed(curve_source=source, provenance=CurveProvenance.UNKNOWN) is False


def test_live_rpc_is_refused_even_with_verified_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert rpc_curve_price_allowed(curve_source="rpc", provenance=CurveProvenance.LIVE_RPC) is False


def test_provenance_argument_is_required() -> None:
    with pytest.raises(TypeError):
        rpc_curve_price_allowed(curve_source="fixture")  # type: ignore[call-arg]
