"""Window metrics over ledger rows: fills, equity curves and the window summary.

Moved from cli/backtest_holdout.py so the upgrade package can summarize a paper window without
importing the CLI. Behaviour is unchanged. fills_from_rows reads FillRecorded rows, row_stamp reads
the epoch stamp of one row, window_curve and summarize_window fold the rows over a genesis state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from pumpgrok.backtest.equity import equity_lamports
from pumpgrok.backtest.metrics import MetricsContext, MetricsReport, summarize
from pumpgrok.config.settings import ConfigError
from pumpgrok.core.adapter import Fill, FillStatus
from pumpgrok.ledger.reducer import LedgerState, reduce
from pumpgrok.replay.clock import parse_ts_utc

__all__ = ["fills_from_rows", "row_stamp", "summarize_window", "window_curve"]


def _fill_from_payload(row: Mapping[str, Any], payload: dict[str, Any]) -> tuple[Fill, Decimal]:
    """One fill and its confirmation latency from a FillRecorded payload, failing closed."""
    money_fields = (
        "filled_lamports",
        "filled_units",
        "realised_slippage_bps",
        "venue_fee_lamports",
        "network_cost_lamports",
        "cash_delta_lamports",
    )
    try:
        money: dict[str, int] = {}
        for name in money_fields:
            raw_amount = payload.get(name, 0)
            if not isinstance(raw_amount, int) or isinstance(raw_amount, bool):
                raise ValueError(f"fill row carries non-integer {name}")
            money[name] = raw_amount
        fraction = Decimal(str(payload["filled_fraction"]))
        status = FillStatus.FILLED if fraction >= 1 else FillStatus.PARTIAL
        order_id = str(payload["order_id"])
        decision_id = str(payload["decision_id"])
        fill = Fill(
            order_id=order_id,
            # Fill validates decision_id as a ULID, so a forced close passes the
            # order id through the constructor and then takes the recorded empty value.
            decision_id=decision_id or order_id,
            status=status,
            venue_tx_ref=str(payload["venue_tx_ref"]),
            filled_lamports=money["filled_lamports"],
            filled_units=money["filled_units"],
            filled_fraction=fraction,
            price_avg=Decimal(str(payload["price_avg"])),
            realised_slippage_bps=money["realised_slippage_bps"],
            venue_fee_lamports=money["venue_fee_lamports"],
            network_cost_lamports=money["network_cost_lamports"],
            route=str(payload.get("route", "curve")),
            ledger_seq=int(row["seq"]),
        )
        if not decision_id:
            fill = fill.model_copy(update={"decision_id": ""})
        return fill, Decimal(str(payload.get("latency_s", "0")))
    except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
        raise ConfigError(["backtest ledger holds an unusable fill row"]) from exc


def fills_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Fill], list[Decimal]]:
    """Fills and confirmation latencies from ledger rows, in ledger order.

    Only FillRecorded rows become fills; other row types never filled.
    Forced closes (graduation, blind flatten) record an empty decision_id
    because no order decision caused them; their Fill keeps that empty
    decision rather than inventing one. Fail closed: a fill row without a
    payload mapping, with non-integer money, or with ids the Fill model
    rejects raises ConfigError.
    """
    fills: list[Fill] = []
    latencies: list[Decimal] = []
    for row in rows:
        if row.get("type") != "FillRecorded":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ConfigError(["backtest ledger holds a fill row without a payload mapping"])
        fill, latency = _fill_from_payload(row, payload)
        fills.append(fill)
        latencies.append(latency)
    return (fills, latencies)


def row_stamp(row: Mapping[str, Any]) -> float:
    """Epoch stamp of one ledger row; an unusable timestamp fails closed."""
    try:
        return parse_ts_utc(str(row["ts_utc"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ConfigError(["paper ledger holds a row with an unusable timestamp"]) from exc


def window_curve(
    genesis: LedgerState,
    rows: Sequence[Mapping[str, Any]],
    deposits: Mapping[int, int] | None = None,
) -> tuple[int, ...]:
    """Equity after each fill, folding every row of the window in ledger order.

    Each fill's point is taken when the next fill begins or the window ends,
    so the settlement rows that follow a fill (position opened or closed,
    marks, refused attempts) count toward it. The final point is therefore
    the equity at window end. There is one point per FillRecorded row, the
    same count the fill list pairs with.
    """
    state = genesis
    curve: list[int] = []
    pending = False
    for row in rows:
        if row.get("type") == "FillRecorded":
            if pending:
                curve.append(equity_lamports(state))
            pending = True
        state = reduce(state, row, deposits)
    if pending:
        curve.append(equity_lamports(state))
    return tuple(curve)


_SETTLEMENT_ROWS = frozenset({"PositionOpened", "PositionClosed"})


def _equity_path(
    genesis: LedgerState,
    rows: Sequence[Mapping[str, Any]],
    deposits: Mapping[int, int] | None = None,
) -> tuple[int, ...]:
    """Equity before the first window row, then at each settled point, in ledger order.

    A settlement is a FillRecorded row and the PositionOpened or PositionClosed row
    appended with it. The fill debits or credits cash before its position row lands,
    so the state between the two is not a settled point and is never recorded.
    Every other row can move equity, including a mark on a position open at the
    window boundary that never produces a fill, so each of those rows is recorded.
    """
    state = genesis
    path = [equity_lamports(state)]
    unsettled = False
    for row in rows:
        kind = row.get("type")
        if unsettled and kind not in _SETTLEMENT_ROWS:
            # A fill that no position row followed is settled as it stands.
            path.append(equity_lamports(state))
        state = reduce(state, row, deposits)
        if kind == "FillRecorded":
            unsettled = True
            continue
        unsettled = False
        path.append(equity_lamports(state))
    if unsettled:
        path.append(equity_lamports(state))
    return tuple(path)


def summarize_window(
    fills: Sequence[Fill],
    *,
    genesis: LedgerState,
    rows: Sequence[Mapping[str, Any]],
    elapsed_days: Decimal,
    deposits: Mapping[int, int] | None = None,
) -> MetricsReport:
    """Window metrics whose return and drawdown cover every row, not only fills.

    summarize takes one equity point per fill, so a window with no fills reads as
    flat and a loss on a position open at the boundary, marked without a fill,
    never reaches total return or drawdown. Those two figures here come from the
    full equity path: return from opening to closing equity, drawdown from the
    running peak over every point. Fill-count statistics stay with summarize.
    """
    path = _equity_path(genesis, rows, deposits)
    opening, closing = path[0], path[-1]
    report = summarize(
        fills,
        MetricsContext(
            initial_equity_lamports=opening,
            equity_curve_lamports=window_curve(genesis, rows, deposits),
            elapsed_days=elapsed_days,
        ),
    )
    total_return = Decimal(closing - opening) / Decimal(opening) if opening > 0 else Decimal(0)
    peak = opening
    max_drawdown = Decimal(0)
    for equity in path:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, Decimal(peak - equity) / Decimal(peak))
    return replace(report, total_return=total_return, max_drawdown=max_drawdown)
