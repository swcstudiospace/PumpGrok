"""Report rendering: byte identity, real windows, honest zeros (BT-05, BT-06).

The report carries the data window, split ids, trial count, real fee
and slippage totals, and the BT-05 metrics. Zero-trade windows render
trade-needing metrics as not-applicable. Deterministic fixtures only;
no network, no wall clock.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pumpgrok.backtest.metrics import MetricsContext, MetricsReport, summarize
from pumpgrok.backtest.report import build_report, render
from pumpgrok.core.adapter import Fill, FillStatus

_ULID_CANON = "01ARZ3NDEKTSV4RRFFQ69G5FAV"

DATA_START = "2026-01-01T00:00:00.000000Z"
DATA_END = "2026-01-01T00:10:00.000000Z"
WINDOW_START = "2026-01-01T00:08:00.000000Z"
WINDOW_END = "2026-01-01T00:10:00.000000Z"

FORBIDDEN = (
    "expected-return",
    "expected-profit",
    "profit",
    "pnl",
    "will-earn",
)


def _ulid(n: int) -> str:
    suffix = f"{n:04d}"
    return _ULID_CANON[: 26 - len(suffix)] + suffix


def _fill(
    n: int,
    filled_lamports: int,
    slippage_bps: int = 0,
    venue_fee: int = 10,
    network_cost: int = 9_000,
) -> Fill:
    return Fill(
        order_id=_ulid(n),
        decision_id=_ulid(900 + n),
        status=FillStatus.FILLED,
        venue_tx_ref=f"dry_run:{_ulid(100 + n)}",
        filled_lamports=filled_lamports,
        filled_units=1_000_000 + n,
        filled_fraction=Decimal("1"),
        price_avg=Decimal("100"),
        realised_slippage_bps=slippage_bps,
        venue_fee_lamports=venue_fee,
        network_cost_lamports=network_cost,
        route="curve",
        ledger_seq=n,
    )


def _metrics(fills: list[Fill]) -> MetricsReport:
    initial = 10_000
    running = initial
    curve: list[int] = []
    for _ in fills:
        running += 100
        curve.append(running)
    return summarize(
        fills,
        MetricsContext(
            initial_equity_lamports=initial,
            equity_curve_lamports=tuple(curve),
            elapsed_days=Decimal("1"),
        ),
    )


def _kwargs(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "run_id": "RUNID",
        "dataset": "smoke",
        "dataset_digest": "D" * 64,
        "seed": 20260101,
        "filter_settings_hash": "0" * 64,
        "param_set_hash": "1" * 64,
        "code_version": "CODE",
        "data_start_utc": DATA_START,
        "data_end_utc": DATA_END,
        "window_start_utc": WINDOW_START,
        "window_end_utc": WINDOW_END,
        "holdout_id": "smoke-holdout",
        "split_ids": ("smoke-train-0", "smoke-train-1", "smoke-holdout"),
        "holdout_events": 2,
        "tuning_events": 3,
        "trial_count": 1,
        "max_eligible_trials": 20,
        "max_allowed_trials": 50,
        "eligible_for_promotion": True,
        "promotion_eligible": False,
        "promotion_reason": "divergence not compared",
        "venue_fee_bps": 100,
        "base_fee_lamports": 5_000,
        "network_cost_lamports": 9_000,
        "elapsed_days": Decimal("1"),
    }
    base.update(overrides)
    return base


def test_rerenders_are_byte_identical() -> None:
    """Two builds from identical inputs render identical bytes."""
    fills = [_fill(1, 1_000, 3), _fill(2, 2_000, 4)]
    first = render(build_report(**_kwargs(fills=fills, metrics=_metrics(fills))))
    second = render(build_report(**_kwargs(fills=fills, metrics=_metrics(fills))))
    assert first == second
    assert first.encode("ascii")


def test_zero_trade_report_is_honest() -> None:
    """Zero trades render ratios as not-applicable with real window identity."""
    text = render(build_report(**_kwargs(fills=[], metrics=_metrics([]))))
    assert text.count("not-applicable") == 4
    assert "total_return: not-applicable" in text
    assert "max_drawdown: not-applicable" in text
    assert "sharpe_ratio: not-applicable" in text
    assert "win_rate: not-applicable" in text
    assert "trade_count: 0" in text
    assert "exposure_lamports: 0" in text
    assert "turnover_lamports: 0" in text
    assert f"data_start_utc: {DATA_START}" in text
    assert f"data_end_utc: {DATA_END}" in text
    assert f"window_start_utc: {WINDOW_START}" in text
    assert f"window_end_utc: {WINDOW_END}" in text
    assert "holdout_id: smoke-holdout" in text
    assert "trial_count: 1" in text
    assert "realized_slippage_bps_total: 0" in text
    assert "realized_fees_lamports_total: 0" in text


def test_filled_report_totals_come_from_fills() -> None:
    """Fee and slippage totals are integer sums over the holdout fills."""
    fills = [_fill(1, 1_000, 3, 100, 9_000), _fill(2, 2_000, 4, 200, 9_000)]
    text = render(build_report(**_kwargs(fills=fills, metrics=_metrics(fills))))
    assert "realized_slippage_bps_total: 7" in text
    assert "realized_fees_lamports_total: 18300" in text
    assert "trade_count: 2" in text
    assert "exposure_lamports: 2000" in text
    assert "turnover_lamports: 3000" in text
    assert "not-applicable" not in text


def test_forbidden_forecast_words_absent() -> None:
    """No forecast wording in zero-trade or filled renders."""
    empty = render(build_report(**_kwargs(fills=[], metrics=_metrics([]))))
    fills = [_fill(1, 1_000, 3)]
    full = render(build_report(**_kwargs(fills=fills, metrics=_metrics(fills))))
    for text in (empty, full):
        lowered = text.lower()
        for word in FORBIDDEN:
            assert word not in lowered
