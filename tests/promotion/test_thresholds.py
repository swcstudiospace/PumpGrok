"""PRM-02 (criterion 6): thresholds load fail-closed; a looser value refuses to load.

The shipped file equals the LiveGate floors. A zero-loss paper record never passes the
profit-factor check (D17-3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.execution.live.live_gate import (
    MAX_DRAWDOWN_FRACTION,
    MIN_CLOSED_TRADES,
    MIN_PAPER_DAYS,
    MIN_PROFIT_FACTOR,
)
from pumpgrok.promotion.thresholds import (
    PaperRecord,
    PromotionThresholdError,
    default_thresholds_path,
    evaluate_paper_record,
    load_thresholds,
)

_VALID = """
[paper]
min_days = {days}
min_closed_trades = {trades}
min_profit_factor = {pf}
max_drawdown_fraction = {dd}
"""


def _write(tmp_path: Path, *, days=14, trades=50, pf=1.2, dd=0.15) -> Path:
    path = tmp_path / "promotion_thresholds.toml"
    path.write_text(_VALID.format(days=days, trades=trades, pf=pf, dd=dd), encoding="utf-8")
    return path


def test_shipped_file_equals_the_live_floors() -> None:
    thresholds = load_thresholds()
    assert default_thresholds_path().is_file()
    assert thresholds.min_paper_days == MIN_PAPER_DAYS
    assert thresholds.min_closed_trades == MIN_CLOSED_TRADES
    assert thresholds.min_profit_factor == MIN_PROFIT_FACTOR
    assert thresholds.max_drawdown_fraction == MAX_DRAWDOWN_FRACTION


def test_missing_file_refuses_to_load(tmp_path: Path) -> None:
    with pytest.raises(PromotionThresholdError, match="unreadable"):
        load_thresholds(tmp_path / "absent.toml")


def test_stricter_values_load(tmp_path: Path) -> None:
    thresholds = load_thresholds(_write(tmp_path, days=30, trades=80, pf=1.5, dd=0.1))
    assert thresholds.min_paper_days == 30
    assert thresholds.max_drawdown_fraction == 0.1


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"days": 13}, "min_days 13"),
        ({"trades": 49}, "min_closed_trades 49"),
        ({"pf": 1.1}, "min_profit_factor 1.1"),
        ({"dd": 0.16}, "max_drawdown_fraction 0.16"),
    ],
)
def test_looser_value_refuses_to_load(
    tmp_path: Path, override: dict[str, float], fragment: str
) -> None:
    path = _write(tmp_path, **override)
    with pytest.raises(PromotionThresholdError, match=fragment):
        load_thresholds(path)


def test_missing_paper_table_refuses_to_load(tmp_path: Path) -> None:
    path = tmp_path / "promotion_thresholds.toml"
    path.write_text("[other]\nmin_days = 14\n", encoding="utf-8")
    with pytest.raises(PromotionThresholdError, match=r"\[paper\]"):
        load_thresholds(path)


def test_non_numeric_value_refuses_to_load(tmp_path: Path) -> None:
    path = _write(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("min_days = 14", 'min_days = "14"'))
    with pytest.raises(PromotionThresholdError, match="min_days"):
        load_thresholds(path)


def _record(**overrides: object) -> PaperRecord:
    values: dict[str, object] = {
        "window_start": "2026-01-01T00:00:00Z",
        "paper_days": 30,
        "closed_trades": 60,
        "gains_lamports": 300,
        "losses_lamports": 100,
        "max_drawdown_fraction": 0.05,
    }
    values.update(overrides)
    return PaperRecord(**values)  # type: ignore[arg-type]


def test_record_meeting_every_threshold_passes() -> None:
    passed, reason = evaluate_paper_record(_record(), load_thresholds())
    assert passed
    assert "meets every threshold" in reason


def test_zero_loss_record_does_not_pass_the_profit_factor_check() -> None:
    record = _record(gains_lamports=600, losses_lamports=0)
    passed, reason = evaluate_paper_record(record, load_thresholds())
    assert not passed
    assert "profit factor undefined" in reason


def test_low_profit_factor_is_refused() -> None:
    passed, reason = evaluate_paper_record(
        _record(gains_lamports=110, losses_lamports=100), load_thresholds()
    )
    assert not passed
    assert "profit factor 1.10 below 1.2" in reason


def test_deep_drawdown_is_refused() -> None:
    passed, reason = evaluate_paper_record(_record(max_drawdown_fraction=0.2), load_thresholds())
    assert not passed
    assert "drawdown 0.200 above 0.15" in reason
