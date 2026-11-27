"""Per-strategy section for daily and weekly reports (OBS-07).

The table is the 16-01 breakdown (realized lamports per strategy) with the
Metrics v2 set. An undefined metric renders as None. annualization_valid is
shown beside the seven metrics; it is a flag, not an eighth metric.

render_strategy_section raises when the rendered parts do not sum to the desk
view. An empty row list renders an empty string, so a period with no strategy
rows leaves the existing report bytes unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from pumpgrok.backtest.metrics import MetricsContext
from pumpgrok.backtest.metrics_v2 import MetricsV2, summarize_v2
from pumpgrok.backtest.roundtrip import UNATTRIBUTED, RoundTrips, breakdown, round_trips
from pumpgrok.ledger.reducer import initial_state, reduce
from pumpgrok.ledger.views import equity_lamports
from pumpgrok.reporting import render as render_mod
from pumpgrok.reporting.render import ReportModel, assert_ascii

__all__ = [
    "METRIC_COLUMNS",
    "DeskView",
    "StrategySectionRow",
    "existing_render_daily",
    "existing_render_weekly",
    "render_strategy_section",
    "section_from_events",
]

#: The decided seven metrics, in owner-decision order. annualization_valid follows them.
METRIC_COLUMNS = (
    "total_return",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "hit_rate",
    "profit_factor",
    "expectancy_lamports",
)

_TITLE = "## Strategies\n"
_HEADER = (
    "strategy | total_return | max_drawdown | sharpe_ratio | sortino_ratio"
    " | hit_rate | profit_factor | expectancy_lamports | annualization_valid"
    " | realized_lamports\n"
)
_ROW = (
    "{strategy} | {total_return} | {max_drawdown} | {sharpe_ratio} | {sortino_ratio}"
    " | {hit_rate} | {profit_factor} | {expectancy_lamports} | {annualization_valid}"
    " | {realized_lamports}\n"
)
_DESK_METRIC = "desk view {name}: {value}\n"
_DESK_TOTAL = "desk view realized_lamports: {total}\n"
_MISMATCH = "per-strategy realized {split} does not sum to desk view {total}"


@dataclass(frozen=True)
class StrategySectionRow:
    """One strategy key from the 16-01 breakdown, with its Metrics v2 reading."""

    strategy: str
    realized_lamports: int
    metrics: MetricsV2


@dataclass(frozen=True)
class DeskView:
    """The unsplit desk total the strategy parts must sum to, plus its Metrics v2."""

    realized_lamports: int
    metrics: MetricsV2


def render_strategy_section(
    rows: Sequence[StrategySectionRow],
    desk_view: DeskView,
) -> str:
    """Render the per-strategy table, or "" when there are no rows.

    Raises ValueError when the rows are non-empty and their realized lamports
    do not sum to the desk view. Undefined metric values render as None.
    """
    if not rows:
        return ""
    split = sum(row.realized_lamports for row in rows)
    if split != desk_view.realized_lamports:
        raise ValueError(_MISMATCH.format(split=split, total=desk_view.realized_lamports))
    parts = [_TITLE, _HEADER]
    for row in rows:
        parts.append(_format_row(row.strategy, row.metrics, row.realized_lamports))
    for name in METRIC_COLUMNS:
        parts.append(
            _DESK_METRIC.format(name=name, value=_format_metric(getattr(desk_view.metrics, name)))
        )
    parts.append(
        _DESK_METRIC.format(
            name="annualization_valid",
            value=_format_flag(desk_view.metrics.annualization_valid),
        )
    )
    parts.append(_DESK_TOTAL.format(total=desk_view.realized_lamports))
    return assert_ascii("".join(parts))


def section_from_events(
    events: Sequence[Mapping[str, Any]],
    refs: Mapping[str, str],
    *,
    start: str,
    end: str,
    elapsed_days: Decimal,
    initial_equity_lamports: int,
    deposits: Mapping[int, int] | None = None,
) -> str:
    """Build the section from a window's ledger rows and ticket refs.

    Returns "" when no closed round trip in the window is attributed to a
    strategy. Unattributed closes are included once any strategy row exists,
    so the breakdown still sums to the desk total. Calls the 16-01 breakdown,
    which raises if that sum fails.
    """
    if not refs:
        return ""
    prefix = [event for event in events if str(event.get("ts_utc", "")) < end]
    book = round_trips(prefix, refs)
    seq_ts = {int(event["seq"]): str(event.get("ts_utc", "")) for event in prefix if "seq" in event}
    closed = tuple(trip for trip in book.closed if start <= seq_ts.get(trip.closed_seq, "") < end)
    if not any(trip.strategy != UNATTRIBUTED for trip in closed):
        return ""
    window = RoundTrips(closed=closed, open_positions=())
    total = sum(trip.realized_lamports for trip in closed)
    return _section_from_breakdown(
        window,
        total,
        _desk_context(
            events,
            start=start,
            end=end,
            elapsed_days=elapsed_days,
            initial_equity_lamports=initial_equity_lamports,
            deposits=deposits,
        ),
        elapsed_days,
    )


def existing_render_daily(model: ReportModel) -> str:
    """The pre-section daily renderer, for a byte compare when no rows exist."""
    return render_mod.render_daily(replace(model, strategy_section=""))


def existing_render_weekly(model: ReportModel) -> str:
    """The pre-section weekly renderer, for a byte compare when no rows exist."""
    return render_mod.render_weekly(replace(model, strategy_section=""))


def _section_from_breakdown(
    book: RoundTrips,
    desk_total: int,
    desk_context: MetricsContext,
    elapsed_days: Decimal,
) -> str:
    parts = breakdown(book, desk_total)
    if not any(strategy != UNATTRIBUTED for strategy in parts):
        return ""
    trip_context = MetricsContext(
        initial_equity_lamports=0,
        equity_curve_lamports=(),
        elapsed_days=elapsed_days,
    )
    rows = tuple(
        StrategySectionRow(
            strategy=strategy,
            realized_lamports=realized,
            metrics=summarize_v2(
                RoundTrips(
                    closed=tuple(trip for trip in book.closed if trip.strategy == strategy),
                    open_positions=(),
                ),
                trip_context,
            ),
        )
        for strategy, realized in parts.items()
    )
    desk_view = DeskView(
        realized_lamports=desk_total,
        metrics=summarize_v2(book, desk_context),
    )
    return render_strategy_section(rows, desk_view)


def _desk_context(
    events: Sequence[Mapping[str, Any]],
    *,
    start: str,
    end: str,
    elapsed_days: Decimal,
    initial_equity_lamports: int,
    deposits: Mapping[int, int] | None,
) -> MetricsContext:
    state = initial_state(
        source="paper",
        initial_equity_lamports=initial_equity_lamports,
        day_utc=start[:10],
    )
    start_equity = initial_equity_lamports
    points: list[int] = []
    for event in events:
        ts = str(event.get("ts_utc", ""))
        if ts >= end:
            break
        state = reduce(state, event, deposits)
        if ts < start:
            start_equity = equity_lamports(state)
            continue
        if event.get("type") == "FillRecorded":
            points.append(equity_lamports(state))
    return MetricsContext(
        initial_equity_lamports=start_equity,
        equity_curve_lamports=tuple(points),
        elapsed_days=elapsed_days,
    )


def _format_row(strategy: str, metrics: MetricsV2, realized: int) -> str:
    values = {name: _format_metric(getattr(metrics, name)) for name in METRIC_COLUMNS}
    return _ROW.format(
        strategy=strategy,
        annualization_valid=_format_flag(metrics.annualization_valid),
        realized_lamports=realized,
        **values,
    )


def _format_metric(value: Decimal | None) -> str:
    if value is None:
        return "None"
    return format(value, "f")


def _format_flag(value: bool) -> str:
    return "true" if value else "false"
