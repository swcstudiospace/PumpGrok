"""Backtest holdout evaluation: window ledger reads, fills, equity paths and holdout metrics.

Split out of cli/backtest.py (11-04). The paper comparison in backtest_paper_gate.py reuses the
window readers defined here, so this module imports nothing from the verb or the paper gate.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pumpgrok.backtest.equity import equity_lamports
from pumpgrok.backtest.evaluate import fold_windows
from pumpgrok.backtest.metrics import MetricsContext, MetricsReport, summarize
from pumpgrok.backtest.results import SharedResult
from pumpgrok.backtest.split import HoldoutSplit
from pumpgrok.config.settings import ConfigError
from pumpgrok.core.adapter import Fill, FillStatus
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch


@dataclass(frozen=True)
class _Dataset:
    """One backtest dataset: report name, replay reference and directory.

    name labels the report and the holdout and fold ids. ref is the identity
    string the manifest, the search and the window replays resolve: the
    fixture name for a bundled dataset, the resolved directory for a recording
    path. directory is that same location as a path, read by load_dataset.
    """

    name: str
    ref: str
    directory: Path


def _read_window_ledger(
    ledger_path: Path, *, verify: bool = False
) -> tuple[list[dict[str, Any]], str | None]:
    """Every row plus the initial-equity meta of one ledger, read-only.

    LedgerStore.read documents itself read-only: no locks, no chain
    mutation. This helper owns open and close around the read. With
    ``verify`` the hash chain is recomputed before any row is read; a
    mismatch raises LedgerInconsistent, which the CLI maps to its ledger exit.
    """
    store = LedgerStore(ledger_path)
    try:
        if verify:
            store.verify()
        rows = store.read(limit=None)
        meta = store.get_meta("initial_equity_lamports")
    finally:
        store.close()
    return (rows, meta)


def _fills_from_rows(
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
    money_fields = (
        "filled_lamports",
        "filled_units",
        "realised_slippage_bps",
        "venue_fee_lamports",
        "network_cost_lamports",
        "cash_delta_lamports",
    )
    for row in rows:
        if row.get("type") != "FillRecorded":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ConfigError(["backtest ledger holds a fill row without a payload mapping"])
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
            fills.append(fill)
            latencies.append(Decimal(str(payload.get("latency_s", "0"))))
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ConfigError(["backtest ledger holds an unusable fill row"]) from exc
    return (fills, latencies)


def _rejection_fees(rows: Sequence[Mapping[str, Any]]) -> int:
    """Fees paid by refused attempts: the OrderRejected fees in the rows.

    The reducer deducts these from cash, so they are real cost even though
    no fill exists for them. Fail closed on a rejection row without a
    payload mapping or with non-integer fees.
    """
    total = 0
    for row in rows:
        if row.get("type") != "OrderRejected":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ConfigError(["backtest ledger holds a rejection row without a payload mapping"])
        fees = payload.get("fees_lamports", 0)
        if not isinstance(fees, int) or isinstance(fees, bool) or fees < 0:
            raise ConfigError(["backtest ledger holds a rejection row with unusable fees"])
        total += fees
    return total


def _row_stamp(row: Mapping[str, Any]) -> float:
    """Epoch stamp of one ledger row; an unusable timestamp fails closed."""
    try:
        return parse_ts_utc(str(row["ts_utc"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ConfigError(["paper ledger holds a row with an unusable timestamp"]) from exc


def _window_curve(genesis: LedgerState, rows: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
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
        state = reduce(state, row)
    if pending:
        curve.append(equity_lamports(state))
    return tuple(curve)


_SETTLEMENT_ROWS = frozenset({"PositionOpened", "PositionClosed"})


def _equity_path(genesis: LedgerState, rows: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
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
        state = reduce(state, row)
        if kind == "FillRecorded":
            unsettled = True
            continue
        unsettled = False
        path.append(equity_lamports(state))
    if unsettled:
        path.append(equity_lamports(state))
    return tuple(path)


def _window_metrics(
    fills: Sequence[Fill],
    *,
    genesis: LedgerState,
    rows: Sequence[Mapping[str, Any]],
    elapsed_days: Decimal,
) -> MetricsReport:
    """Window metrics whose return and drawdown cover every row, not only fills.

    summarize takes one equity point per fill, so a window with no fills reads as
    flat and a loss on a position open at the boundary, marked without a fill,
    never reaches total return or drawdown. Those two figures here come from the
    full equity path: return from opening to closing equity, drawdown from the
    running peak over every point. Fill-count statistics stay with summarize.
    """
    path = _equity_path(genesis, rows)
    opening, closing = path[0], path[-1]
    report = summarize(
        fills,
        MetricsContext(
            initial_equity_lamports=opening,
            equity_curve_lamports=_window_curve(genesis, rows),
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


def _last_row_stamp(rows: Sequence[Mapping[str, Any]]) -> float:
    """Latest stamp over every row of the holdout ledger, settling orders included.

    Replay advances the clock while an order confirms, so a settlement row can
    land past the last recorded tick. An empty ledger fails closed: replay
    always writes its checkpoint verdict row, so an empty one means a broken run.
    """
    if not rows:
        raise ConfigError(["backtest holdout ledger holds no rows"])
    return max(_row_stamp(row) for row in rows)


def _window_end(last_stamp: float) -> float:
    """Half-open window end: the first float past the latest holdout row.

    The holdout summary and the paper comparison both take their end from
    this one rule, so they count the same fills and marks.
    """
    return math.nextafter(last_stamp, math.inf)


@dataclass(frozen=True)
class _HoldoutOutcome:
    """Evaluated holdout window: fills, metrics and report identity."""

    fills: list[Fill]
    latencies: list[Decimal]
    window_metrics: MetricsReport
    backtest_result: SharedResult
    elapsed_days: Decimal
    data_start_utc: str
    data_end_utc: str
    window_start_utc: str
    window_end_utc: str
    window_end_ts: float
    rejected_fees_lamports: int


def _evaluate_holdout(
    *,
    spec: _Dataset,
    dataset: FixtureDataset,
    stamps: tuple[float, ...],
    split: HoldoutSplit,
    run_id: str,
    holdout_ledger: Path,
    initial_fallback: int,
) -> _HoldoutOutcome:
    """Summarize the holdout fills of the ledger that run_search already replayed (BT-05, BT-06).

    The window comes from fold_windows with the same fold count the search
    used, so tuning never reads past the cutoff; the identity check against
    the split fails closed on drift. Fills rebuild from the recorded
    FillRecorded rows, the equity curve folds every window row from genesis,
    and the span between the first and last window event sets the elapsed
    days. The window ends at the first float past the latest holdout row,
    settling orders included; the shared result and the paper comparison use that end.
    """
    cutoff = split.holdout_start_ts
    windows = fold_windows(stamps, spec.name, 3)
    holdout_window = windows.holdout
    if holdout_window.window_id != split.holdout_id:
        raise ConfigError(["backtest holdout window identity drifted"])
    rows, meta = _read_window_ledger(holdout_ledger)
    last_row_stamp = _last_row_stamp(rows)
    window_end_ts = _window_end(last_row_stamp)
    fills, latencies = _fills_from_rows(rows)
    initial = int(meta) if meta is not None else initial_fallback
    genesis = initial_state(source="backtest", initial_equity_lamports=initial, day_utc="")
    events = dataset.events
    window_points = [
        (event_epoch(event), str(event["ts_utc"]))
        for event in events
        if event_epoch(event) >= cutoff
    ]
    if window_points:
        window_start_utc = window_points[0][1]
        first_stamp = window_points[0][0]
        last_stamp = window_points[-1][0]
    else:
        window_start_utc = format_ts_utc(cutoff)
        first_stamp = cutoff
        last_stamp = cutoff
    if last_stamp > first_stamp:
        elapsed_days = (Decimal(str(last_stamp)) - Decimal(str(first_stamp))) / Decimal(86400)
    else:
        elapsed_days = Decimal(0)
    window_metrics = _window_metrics(fills, genesis=genesis, rows=rows, elapsed_days=elapsed_days)
    backtest_result = SharedResult.from_fills(
        run_id=run_id,
        dataset=spec.name,
        window_start_ts=cutoff,
        window_end_ts=window_end_ts,
        fills=fills,
        latencies=latencies,
    )
    return _HoldoutOutcome(
        fills=fills,
        latencies=latencies,
        window_metrics=window_metrics,
        backtest_result=backtest_result,
        elapsed_days=elapsed_days,
        data_start_utc=str(events[0]["ts_utc"]),
        data_end_utc=str(events[-1]["ts_utc"]),
        window_start_utc=window_start_utc,
        window_end_utc=format_ts_utc(last_row_stamp),
        window_end_ts=window_end_ts,
        rejected_fees_lamports=_rejection_fees(rows),
    )
