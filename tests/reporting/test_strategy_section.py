"""Per-strategy report section: multi-strategy sum equality, daily+weekly."""

from __future__ import annotations

from pumpgrok.backtest.roundtrip import RoundTripFill, group_round_trips, per_strategy_breakdown
from pumpgrok.reporting.render import ReportModel, render_daily, render_weekly
from pumpgrok.reporting.strategy_section import per_strategy_summary, render_strategy_section


def _fills() -> list[RoundTripFill]:
    return [
        RoundTripFill("A", "buy", 100, "legacy_screening"),
        RoundTripFill("A", "sell", 130, "legacy_screening"),
        RoundTripFill("B", "buy", 200, "mean_reversion"),
        RoundTripFill("B", "sell", 180, "mean_reversion"),
        RoundTripFill("C", "buy", 50, "momentum_breakout"),
        RoundTripFill("C", "sell", 50, "momentum_breakout"),
    ]


def test_parts_sum_exactly_to_desk_view() -> None:
    result = group_round_trips(_fills())
    breakdown = per_strategy_breakdown(result)
    assert breakdown == {"legacy_screening": 30, "mean_reversion": -20, "momentum_breakout": 0}
    assert sum(breakdown.values()) == result.total_realized_net_lamports == 10


def test_section_renders_and_sums() -> None:
    breakdown = per_strategy_breakdown(group_round_trips(_fills()))
    section, total = per_strategy_summary(breakdown)
    assert total == 10
    for strategy_id in breakdown:
        assert strategy_id in section
    assert "desk total" in section


def test_daily_and_weekly_both_carry_section() -> None:
    breakdown = per_strategy_breakdown(group_round_trips(_fills()))
    section = render_strategy_section(breakdown)
    model = ReportModel(day="2026-01-01", strategy_section=section)
    assert "## Per-strategy" in render_daily(model)
    assert "## Per-strategy" in render_weekly(model)
    # Empty breakdown renders the empty line, never a zero total row.
    empty, total = per_strategy_summary({})
    assert "none closed in this window" in empty
    assert total == 0
