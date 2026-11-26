<<<<<<< HEAD
"""Per-strategy report section for daily and weekly reports (OBS-07; D-09).

The section lists per-strategy net lamports, win rate and round-trip
count from round-trip grouping; the parts sum EXACTLY to the desk-view
total (integer equality, never rounding). Paper-only: this module only
renders text -- no send path, no network.
=======
"""Per-strategy section for daily and weekly reports (OBS-07).

The table is the 16-01 breakdown (realized lamports per strategy) with the
Metrics v2 set. An undefined metric renders as None. annualization_valid is
shown beside the seven metrics; it is a flag, not an eighth metric.

render_strategy_section raises when the rendered parts do not sum to the desk
view. An empty row list renders an empty string, so a period with no strategy
rows leaves the existing report bytes unchanged.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from collections.abc import Mapping

from pumpgrok.reporting.render import sol as _render_sol

__all__ = ["per_strategy_summary", "render_strategy_section"]

_HEADER = "## Per-strategy\nstrategy | net SOL | win rate | trips\n"
_ROW = "{strategy} | {net} | {win_rate} | {trips}\n"
_TOTAL = "desk total | {net} SOL | {win_rate} | {trips}\n"


def _sol(lamports: int) -> str:
    return _render_sol(lamports)


def per_strategy_summary(
    trips_by_strategy: Mapping[str, int],
    win_rates: Mapping[str, float] | None = None,
    trip_counts: Mapping[str, int] | None = None,
) -> tuple[str, int]:
    """Markdown section plus the desk total it sums to (exact integer sum).

    ``trips_by_strategy`` maps strategy id to realized net lamports;
    the returned total is the exact integer sum of its values.
    """
    lines = [_HEADER]
    total = 0
    total_trips = 0
    for strategy_id in sorted(trips_by_strategy):
        net = int(trips_by_strategy[strategy_id])
        total += net
        trips = int((trip_counts or {}).get(strategy_id, 0))
        total_trips += trips
        win_rate = (win_rates or {}).get(strategy_id, "n/a")
        lines.append(
            _ROW.format(strategy=strategy_id, net=_sol(net), win_rate=win_rate, trips=trips)
        )
    if not trips_by_strategy:
        lines.append("none closed in this window\n")
    else:
        lines.append(_TOTAL.format(net=_sol(total), win_rate="n/a", trips=total_trips))
    return "".join(lines), total


def render_strategy_section(
    trips_by_strategy: Mapping[str, int],
    win_rates: Mapping[str, float] | None = None,
    trip_counts: Mapping[str, int] | None = None,
) -> str:
    """Markdown section only (see :func:`per_strategy_summary` for totals)."""
    section, _ = per_strategy_summary(trips_by_strategy, win_rates, trip_counts)
    return section
=======
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from weakref import WeakKeyDictionary

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
    "bind_strategy_section",
    "existing_render_daily",
    "existing_render_weekly",
    "render_strategy_section",
    "section_from_events",
    "strategy_section_of",
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

_SECTIONS: WeakKeyDictionary[ReportModel, str] = WeakKeyDictionary()
_ORIGINAL_DAILY = render_mod.render_daily
_ORIGINAL_WEEKLY = render_mod.render_weekly


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


def bind_strategy_section(model: ReportModel, section: str) -> None:
    """Remember a non-empty section so the daily renderer can append it."""
    if section:
        _SECTIONS[model] = section


def strategy_section_of(model: ReportModel) -> str:
    """The section bound to a model, or "" when that period has no strategy rows."""
    return _SECTIONS.get(model, "")


def existing_render_daily(model: ReportModel) -> str:
    """The pre-section daily renderer, for a byte compare when no rows exist."""
    return _ORIGINAL_DAILY(model)


def existing_render_weekly(model: ReportModel) -> str:
    """The pre-section weekly renderer, for a byte compare when no rows exist."""
    saved = render_mod.render_daily
    render_mod.render_daily = _ORIGINAL_DAILY
    try:
        return _ORIGINAL_WEEKLY(model)
    finally:
        render_mod.render_daily = saved


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


def _render_daily_with_section(model: ReportModel) -> str:
    body = _ORIGINAL_DAILY(model)
    section = _SECTIONS.get(model, "")
    if not section:
        return body
    return assert_ascii(body + "\n" + section)


render_mod.render_daily = _render_daily_with_section
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
