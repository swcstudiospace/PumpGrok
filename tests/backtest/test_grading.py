"""Grading: only recorded + complete + long + gap-light passes."""

from __future__ import annotations

from pumpgrok.backtest.grading import DataKind, DatasetMeta, grade


def _meta(**overrides: object) -> DatasetMeta:
    base: dict[str, object] = {
        "kind": DataKind.RECORDED,
        "complete": True,
        "duration_days": 45.0,
        "gap_count": 1,
    }
    base.update(overrides)  # type: ignore[arg-type]
    return DatasetMeta(**base)  # type: ignore[arg-type]


def test_recorded_complete_long_gap_light_passes() -> None:
    result = grade(_meta())
    assert result.eligible is True
    assert result.reasons == ("pass",)


def test_traded_only_never_promotes() -> None:
    assert grade(_meta(kind=DataKind.TRADED_ONLY)).eligible is False


def test_fixture_never_promotes() -> None:
    assert grade(_meta(kind=DataKind.FIXTURE)).eligible is False


def test_hand_authored_never_promotes() -> None:
    assert grade(_meta(kind=DataKind.HAND_AUTHORED)).eligible is False


def test_short_or_incomplete_or_gappy_fails() -> None:
    assert grade(_meta(duration_days=10.0)).eligible is False
    assert grade(_meta(complete=False)).eligible is False
    assert grade(_meta(gap_count=9)).eligible is False


def test_each_failure_is_named() -> None:
    reasons = grade(_meta(kind=DataKind.FIXTURE, duration_days=1.0)).reasons
    assert any("fixture" in reason for reason in reasons)
    assert any("duration" in reason for reason in reasons)
