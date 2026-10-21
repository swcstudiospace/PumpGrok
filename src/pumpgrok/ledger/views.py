"""Derived views over LedgerState plus the event tail (paper-engine.md 3.4).

Every money view returns ``int`` lamports, every ratio a ``Decimal``. Views
never touch the store; restart and reporting fold first, then read here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from pumpgrok.ledger.reducer import LedgerState, PositionView, reduce


def cash_lamports(state: LedgerState) -> int:
    """Spendable cash in lamports."""
    return int(state.cash_lamports)


def positions(state: LedgerState) -> dict[str, PositionView]:
    """Open positions (token_units > 0)."""
    return {mint: pos for mint, pos in state.positions.items() if pos.token_units > 0}


def unrealized_pnl_lamports(state: LedgerState) -> int:
    """Sum of last-MTM minus cost basis over open positions."""
    return sum(pos.last_mtm_lamports - pos.cost_basis_lamports for pos in positions(state).values())


def equity_lamports(state: LedgerState) -> int:
    """Cash plus open-position marks."""
    return int(state.cash_lamports) + sum(
        pos.last_mtm_lamports for pos in positions(state).values()
    )


def drawdown_fraction(state: LedgerState) -> Decimal:
    """(peak - equity) / peak; zero when peak is zero."""
    peak = int(state.peak_equity_lamports)
    if peak <= 0:
        return Decimal("0")
    return Decimal(peak - equity_lamports(state)) / Decimal(peak)


def daily_pnl_fraction(state: LedgerState) -> Decimal:
    """(equity - day_start) / day_start; zero when day-start is zero."""
    start = int(state.day_start_equity_lamports)
    if start <= 0:
        return Decimal("0")
    return Decimal(equity_lamports(state) - start) / Decimal(start)


def _closed_in_range(
    events: Sequence[Mapping[str, Any]], since_ts: str, until_ts: str
) -> list[dict[str, Any]]:
    out = []
    for event in events:
        if event.get("type") != "PositionClosed":
            continue
        ts = str(event.get("ts_utc", ""))
        if since_ts <= ts < until_ts:
            payload = event.get("payload")
            row = dict(payload) if isinstance(payload, Mapping) else {}
            row["_ts_utc"] = ts
            out.append(row)
    return out


def realized_pnl_lamports(
    events: Sequence[Mapping[str, Any]], *, since_ts: str, until_ts: str
) -> int:
    """Sum of PositionClosed realized PnL in [since_ts, until_ts)."""
    return sum(
        int(row.get("realized_pnl_lamports", 0))
        for row in _closed_in_range(events, since_ts, until_ts)
    )


def fees_lamports(events: Sequence[Mapping[str, Any]], *, since_ts: str, until_ts: str) -> int:
    """Venue plus network fees on fills and rejections in the window."""
    total = 0
    for event in events:
        ts = str(event.get("ts_utc", ""))
        if not since_ts <= ts < until_ts:
            continue
        payload = event.get("payload")
        row = dict(payload) if isinstance(payload, Mapping) else {}
        if event.get("type") == "FillRecorded":
            total += int(row.get("venue_fee_lamports", 0)) + int(
                row.get("network_cost_lamports", 0)
            )
        elif event.get("type") == "OrderRejected":
            total += int(row.get("fees_lamports", 0))
    return total


def equity_curve(
    events: Sequence[Mapping[str, Any]], genesis: LedgerState
) -> list[tuple[str, int]]:
    """(ts, equity) after every fill and mark, by refolding the tail."""
    state = genesis
    curve: list[tuple[str, int]] = []
    for event in events:
        state = reduce(state, event)
        if event.get("type") in ("FillRecorded", "OrderRejected", "MarkToMarket"):
            curve.append((str(event.get("ts_utc", "")), equity_lamports(state)))
    return curve


def win_rate(
    events: Sequence[Mapping[str, Any]], *, since_ts: str, until_ts: str
) -> Decimal | None:
    """Fraction of closed trades with positive realized PnL; None when none closed."""
    closed = _closed_in_range(events, since_ts, until_ts)
    if not closed:
        return None
    winners = sum(1 for row in closed if int(row.get("realized_pnl_lamports", 0)) > 0)
    return Decimal(winners) / Decimal(len(closed))


def profit_factor(events: Sequence[Mapping[str, Any]], *, since_ts: str, until_ts: str) -> str:
    """Sum(gains) / abs(sum(losses)); "n/a" when there are no losses."""
    closed = _closed_in_range(events, since_ts, until_ts)
    gains = sum(
        int(row.get("realized_pnl_lamports", 0))
        for row in closed
        if int(row.get("realized_pnl_lamports", 0)) > 0
    )
    losses = sum(
        int(row.get("realized_pnl_lamports", 0))
        for row in closed
        if int(row.get("realized_pnl_lamports", 0)) < 0
    )
    if losses == 0:
        return "n/a"
    return str(Decimal(gains) / Decimal(abs(losses)))
