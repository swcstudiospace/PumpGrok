"""Backtest holdout evaluation: window ledger reads, fills, equity paths and holdout metrics.

Split out of cli/backtest.py (11-04). The paper comparison in backtest_paper_gate.py reuses the
window readers defined here, so this module imports nothing from the verb or the paper gate.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.backtest.evaluate import fold_windows
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.backtest.results import SharedResult
from pumpgrok.backtest.split import HoldoutSplit
from pumpgrok.config.settings import ConfigError
from pumpgrok.core.adapter import Fill
from pumpgrok.execution.deposits import position_deposits_by_seq
from pumpgrok.ledger.reducer import initial_state
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch
from pumpgrok.upgrade.window_metrics import fills_from_rows, row_stamp, summarize_window


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
) -> tuple[list[dict[str, Any]], str | None, dict[int, int]]:
    """Every row, the initial-equity meta and each opening's ATA deposit, read-only.

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
        deposits = position_deposits_by_seq(store)
    finally:
        store.close()
    return (rows, meta, deposits)


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


def _last_row_stamp(rows: Sequence[Mapping[str, Any]]) -> float:
    """Latest stamp over every row of the holdout ledger, settling orders included.

    Replay advances the clock while an order confirms, so a settlement row can
    land past the last recorded tick. An empty ledger fails closed: replay
    always writes its checkpoint verdict row, so an empty one means a broken run.
    """
    if not rows:
        raise ConfigError(["backtest holdout ledger holds no rows"])
    return max(row_stamp(row) for row in rows)


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


def _window_span(events: Sequence[dict[str, Any]], cutoff: float) -> tuple[str, float, float]:
    """Window start timestamp and the first and last epoch stamps at or after the cutoff."""
    window_points = [
        (event_epoch(event), str(event["ts_utc"]))
        for event in events
        if event_epoch(event) >= cutoff
    ]
    if window_points:
        return (window_points[0][1], window_points[0][0], window_points[-1][0])
    return (format_ts_utc(cutoff), cutoff, cutoff)


def _elapsed_days(first_stamp: float, last_stamp: float) -> Decimal:
    """Days between the first and last window stamps; zero when the span is empty or inverted."""
    if last_stamp > first_stamp:
        return (Decimal(str(last_stamp)) - Decimal(str(first_stamp))) / Decimal(86400)
    return Decimal(0)


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
    rows, meta, deposits = _read_window_ledger(holdout_ledger)
    last_row_stamp = _last_row_stamp(rows)
    window_end_ts = _window_end(last_row_stamp)
    fills, latencies = fills_from_rows(rows)
    initial = int(meta) if meta is not None else initial_fallback
    genesis = initial_state(source="backtest", initial_equity_lamports=initial, day_utc="")
    events = dataset.events
    window_start_utc, first_stamp, last_stamp = _window_span(events, cutoff)
    elapsed_days = _elapsed_days(first_stamp, last_stamp)
    window_metrics = summarize_window(
        fills, genesis=genesis, rows=rows, elapsed_days=elapsed_days, deposits=deposits
    )
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
