"""Per-strategy report section for daily and weekly reports (OBS-07; D-09).

The section lists per-strategy net lamports, win rate and round-trip
count from round-trip grouping; the parts sum EXACTLY to the desk-view
total (integer equality, never rounding). Paper-only: this module only
renders text -- no send path, no network.
"""

from __future__ import annotations

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
        lines.append(
            _TOTAL.format(net=_sol(total), win_rate="n/a", trips=total_trips)
        )
    return "".join(lines), total


def render_strategy_section(
    trips_by_strategy: Mapping[str, int],
    win_rates: Mapping[str, float] | None = None,
    trip_counts: Mapping[str, int] | None = None,
) -> str:
    """Markdown section only (see :func:`per_strategy_summary` for totals)."""
    section, _ = per_strategy_summary(trips_by_strategy, win_rates, trip_counts)
    return section
