"""Graduation and data gaps must not manufacture a paper sale."""

import pytest

from pumpgrok.datafeed.graduation import GapSettings, PositionAction, entry_allowed, position_action
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.tools.onchain import curve_layout


def snapshot(*, complete: bool = False, source: str = "rpc") -> CurveSnapshot:
    return CurveSnapshot(
        mint="mint-1", s_lamports=42_000_000_000, t_units=766_428_571_428_571,
        complete=complete, source=source, ts=100.0,
    )


def test_open_verified_curve_allows_entry_but_completed_curve_denies_it(monkeypatch):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "VERIFIED")
    assert entry_allowed(snapshot()) is True
    assert entry_allowed(snapshot(complete=True)) is False
    assert entry_allowed(None) is False


def test_assumed_or_unknown_live_curve_never_authorizes_entry(monkeypatch):
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    assert entry_allowed(snapshot()) is False
    assert entry_allowed(snapshot(source="unknown")) is False
    assert entry_allowed(snapshot(source="fixture")) is True


def test_gap_holds_then_timeout_marks_zero_without_a_sale():
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    assert position_action(snapshot(), last_trusted_at=100.0, now=100.0, settings=settings) == PositionAction.MARK
    assert position_action(None, last_trusted_at=100.0, now=110.0, settings=settings) == PositionAction.HOLD
    assert position_action(None, last_trusted_at=100.0, now=129.999, settings=settings) == PositionAction.HOLD
    assert position_action(None, last_trusted_at=100.0, now=130.0, settings=settings) == PositionAction.ZERO_MARK


def test_completed_curve_is_distinct_from_gap_and_timeout():
    settings = GapSettings(gap_after_s=10.0, timeout_after_s=30.0)
    assert position_action(snapshot(complete=True), last_trusted_at=100.0, now=101.0, settings=settings) == PositionAction.GRADUATED


@pytest.mark.parametrize(
    ("gap", "timeout"),
    [(0, 30), (-1, 30), (10, 0), (10, 9), (float("nan"), 30), (10, float("inf"))],
)
def test_gap_and_timeout_settings_are_validated(gap, timeout):
    with pytest.raises(ValueError):
        GapSettings(gap_after_s=gap, timeout_after_s=timeout)
