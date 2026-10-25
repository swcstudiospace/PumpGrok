"""Deterministic backtest Markdown report (BT-05, BT-06; CONTEXT D-09 and G-01).

`render` produces byte-identical Markdown for identical inputs: sorted
keys, fixed integer formatting, plain decimal formatting, and no
wall-clock timestamps. The report names the data window from recorded
event timestamps, the holdout id and split ids, the trial count with
both limits, realized slippage and fee totals summed from holdout
fills, the BT-05 window metrics with their inputs and assumptions, the
promotion eligibility flag with its reason, and the paper comparison
section when a paper ledger was supplied.

Money stays integer base units; Decimal appears only for ratios.
Windows with zero trades render trade-needing metrics as
not-applicable while trade count, exposure and turnover render as 0.
Every figure describes the recorded evaluation, never a forecast.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal

from pumpgrok.backtest.divergence import DivergenceVerdict
from pumpgrok.backtest.metrics import ANNUALIZATION_DAYS_PER_YEAR, MetricsReport
from pumpgrok.core.adapter import Fill

__all__ = [
    "NOT_APPLICABLE",
    "BacktestReport",
    "build_report",
    "render",
    "with_divergence",
]

#: Rendered text for a metric the window cannot define (D-C5). Ratios
#: against an empty fill window are undefined, so they never render
#: as measured zero flat performance.
NOT_APPLICABLE = "not-applicable"


@dataclass(frozen=True)
class BacktestReport:
    """Pure data for one backtest report: no I/O, built by the CLI verb.

    run_id derives from the run manifest; dataset names the recorded
    fixture; digests and hashes identify exact inputs. data_start_utc
    and data_end_utc bound the full recorded dataset; window_start_utc
    and window_end_utc bound the holdout window replayed once; all four
    come from recorded event timestamps, never the wall clock.
    holdout_id names the holdout window and split_ids names the train
    ids plus the holdout id; holdout_events and tuning_events count
    recorded ticks on each side of the cutoff. trial_count is the
    ledger size after this run recorded its trial. Fee schedule fields
    quote the desk fee model; realized totals are summed from holdout
    fills. Metric fields carry the BT-05 window summary, with
    trade-needing ratios as None on zero-trade windows. Paper fields
    carry the same-window paper summary when a paper ledger was
    supplied, else None. promotion_reason states why promotion is or
    is not eligible.
    """

    run_id: str
    dataset: str
    dataset_digest: str
    seed: int
    filter_settings_hash: str
    param_set_hash: str
    code_version: str
    holdout_id: str
    holdout_events: int
    tuning_events: int
    trial_count: int
    max_eligible_trials: int
    max_allowed_trials: int
    eligible_for_promotion: bool
    promotion_eligible: bool
    venue_fee_bps: int
    base_fee_lamports: int
    network_cost_lamports: int
    realized_slippage_bps_total: int
    realized_fees_lamports_total: int
    data_start_utc: str = ""
    data_end_utc: str = ""
    window_start_utc: str = ""
    window_end_utc: str = ""
    split_ids: tuple[str, ...] = ()
    promotion_reason: str = "divergence not compared"
    total_return: Decimal | None = None
    max_drawdown: Decimal | None = None
    sharpe_ratio: Decimal | None = None
    win_rate: Decimal | None = None
    trade_count: int = 0
    exposure_lamports: int = 0
    turnover_lamports: int = 0
    elapsed_days: Decimal = Decimal("0")
    paper_total_return: Decimal | None = None
    paper_sharpe_ratio: Decimal | None = None
    paper_trade_count: int | None = None
    divergence_reasons: tuple[str, ...] = ()


def build_report(
    *,
    run_id: str,
    dataset: str,
    dataset_digest: str,
    seed: int,
    filter_settings_hash: str,
    param_set_hash: str,
    code_version: str,
    data_start_utc: str,
    data_end_utc: str,
    window_start_utc: str,
    window_end_utc: str,
    holdout_id: str,
    split_ids: Sequence[str],
    holdout_events: int,
    tuning_events: int,
    trial_count: int,
    max_eligible_trials: int,
    max_allowed_trials: int,
    eligible_for_promotion: bool,
    promotion_eligible: bool,
    promotion_reason: str,
    venue_fee_bps: int,
    base_fee_lamports: int,
    network_cost_lamports: int,
    fills: Sequence[Fill],
    metrics: MetricsReport,
    elapsed_days: Decimal,
    paper_metrics: MetricsReport | None = None,
    divergence_reasons: Sequence[str] = (),
) -> BacktestReport:
    """Assemble one report from holdout fills and their window summary.

    Slippage and fee totals are summed from the fills in ledger order:
    slippage sums realised_slippage_bps, fees sum venue plus network
    costs. When the window holds no trades the trade-needing ratios
    (return, drawdown, Sharpe-style ratio, win rate) map to None and
    render as not-applicable; trade count, exposure and turnover stay
    defined sums and render as 0. The paper summary maps the same way
    when supplied.
    """
    slippage_total = sum(fill.realised_slippage_bps for fill in fills)
    fees_total = sum(fill.venue_fee_lamports + fill.network_cost_lamports for fill in fills)
    if metrics.trade_count == 0:
        total_return: Decimal | None = None
        max_drawdown: Decimal | None = None
        sharpe_ratio: Decimal | None = None
        win_rate: Decimal | None = None
    else:
        total_return = metrics.total_return
        max_drawdown = metrics.max_drawdown
        sharpe_ratio = metrics.sharpe_ratio
        win_rate = metrics.win_rate
    if paper_metrics is None:
        paper_return: Decimal | None = None
        paper_sharpe: Decimal | None = None
        paper_trades: int | None = None
    elif paper_metrics.trade_count == 0:
        paper_return = None
        paper_sharpe = None
        paper_trades = 0
    else:
        paper_return = paper_metrics.total_return
        paper_sharpe = paper_metrics.sharpe_ratio
        paper_trades = paper_metrics.trade_count
    return BacktestReport(
        run_id=run_id,
        dataset=dataset,
        dataset_digest=dataset_digest,
        seed=seed,
        filter_settings_hash=filter_settings_hash,
        param_set_hash=param_set_hash,
        code_version=code_version,
        holdout_id=holdout_id,
        holdout_events=holdout_events,
        tuning_events=tuning_events,
        trial_count=trial_count,
        max_eligible_trials=max_eligible_trials,
        max_allowed_trials=max_allowed_trials,
        eligible_for_promotion=eligible_for_promotion,
        promotion_eligible=promotion_eligible,
        venue_fee_bps=venue_fee_bps,
        base_fee_lamports=base_fee_lamports,
        network_cost_lamports=network_cost_lamports,
        realized_slippage_bps_total=slippage_total,
        realized_fees_lamports_total=fees_total,
        data_start_utc=data_start_utc,
        data_end_utc=data_end_utc,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        split_ids=tuple(split_ids),
        promotion_reason=promotion_reason,
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        win_rate=win_rate,
        trade_count=metrics.trade_count,
        exposure_lamports=metrics.exposure_lamports,
        turnover_lamports=metrics.turnover_lamports,
        elapsed_days=elapsed_days,
        paper_total_return=paper_return,
        paper_sharpe_ratio=paper_sharpe,
        paper_trade_count=paper_trades,
        divergence_reasons=tuple(divergence_reasons),
    )


def with_divergence(report: BacktestReport, verdict: DivergenceVerdict) -> BacktestReport:
    """Apply a divergence verdict to a report (G-08 flag half).

    A blocking verdict clears promotion_eligible; a clean verdict leaves
    the report unchanged. The stderr line and exit code halves live with
    the caller via `breach_line` and `enforce`.
    """
    if not verdict.blocks_promotion:
        return report
    return replace(report, promotion_eligible=False)


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _decimal(value: Decimal | None) -> str:
    """Fixed plain-decimal text, or not-applicable for an undefined window metric."""
    if value is None:
        return NOT_APPLICABLE
    return format(value, "f")


def render(report: BacktestReport) -> str:
    """Render the deterministic Markdown document for one backtest report."""
    run_rows = sorted(
        {
            "code_version": report.code_version,
            "dataset": report.dataset,
            "dataset_digest": report.dataset_digest,
            "filter_settings_hash": report.filter_settings_hash,
            "param_set_hash": report.param_set_hash,
            "run_id": report.run_id,
            "seed": str(report.seed),
        }.items()
    )
    window_rows = sorted(
        {
            "data_end_utc": report.data_end_utc,
            "data_start_utc": report.data_start_utc,
            "holdout_events": str(report.holdout_events),
            "holdout_id": report.holdout_id,
            "split_ids": ",".join(report.split_ids),
            "tuning_events": str(report.tuning_events),
            "window_end_utc": report.window_end_utc,
            "window_start_utc": report.window_start_utc,
        }.items()
    )
    trial_rows = sorted(
        {
            "trial_limit_eligible": _bool(report.eligible_for_promotion),
            "max_allowed_trials": str(report.max_allowed_trials),
            "max_eligible_trials": str(report.max_eligible_trials),
            "trial_count": str(report.trial_count),
        }.items()
    )
    metric_rows = sorted(
        {
            "elapsed_days": format(report.elapsed_days, "f"),
            "exposure_lamports": str(report.exposure_lamports),
            "max_drawdown": _decimal(report.max_drawdown),
            "sharpe_annualization_days_per_year": str(ANNUALIZATION_DAYS_PER_YEAR),
            "sharpe_ratio": _decimal(report.sharpe_ratio),
            "total_return": _decimal(report.total_return),
            "trade_count": str(report.trade_count),
            "turnover_lamports": str(report.turnover_lamports),
            "win_rate": _decimal(report.win_rate),
        }.items()
    )
    fee_rows = sorted(
        {
            "base_fee_lamports": str(report.base_fee_lamports),
            "network_cost_lamports": str(report.network_cost_lamports),
            "realized_fees_lamports_total": str(report.realized_fees_lamports_total),
            "venue_fee_bps": str(report.venue_fee_bps),
        }.items()
    )
    parts: list[str] = ["# PumpGrok backtest report\n"]
    parts.append("## Run\n")
    parts.extend(f"{key}: {value}\n" for key, value in run_rows)
    parts.append("## Data window\n")
    parts.extend(f"{key}: {value}\n" for key, value in window_rows)
    parts.append("## Trials\n")
    parts.extend(f"{key}: {value}\n" for key, value in trial_rows)
    parts.append("## Metrics\n")
    parts.extend(f"{key}: {value}\n" for key, value in metric_rows)
    parts.append(
        "note: BT-05 window metrics from holdout fills in ledger order; "
        "inputs are the holdout fills, the cash-delta equity curve from "
        "recorded fills, and the window span in days\n"
    )
    parts.append(
        "note: assumptions are fees already reflected in the curve, marks "
        "invisible between fills, fills spread evenly for annualization, "
        "and a zero baseline rate\n"
    )
    parts.append(
        "note: sharpe-style ratio annualizes with ANNUALIZATION_DAYS_PER_YEAR; "
        "crypto markets trade 24/7 with no close days\n"
    )
    parts.append("## Slippage\n")
    parts.append(f"realized_slippage_bps_total: {report.realized_slippage_bps_total}\n")
    parts.append("note: sum of realised_slippage_bps over holdout fills in ledger order\n")
    parts.append("## Fees\n")
    parts.extend(f"{key}: {value}\n" for key, value in fee_rows)
    parts.append(
        "note: realized total is venue plus network costs summed over "
        "holdout fills; schedule fields quote the desk fee model\n"
    )
    parts.append("## Verdict\n")
    parts.append(f"promotion_eligible: {_bool(report.promotion_eligible)}\n")
    parts.append(f"promotion_reason: {report.promotion_reason}\n")
    parts.append("## Paper comparison\n")
    if report.paper_trade_count is None:
        parts.append("paper_comparison: not compared\n")
    else:
        paper_rows = sorted(
            {
                "divergence_reasons": (
                    "|".join(report.divergence_reasons) if report.divergence_reasons else "none"
                ),
                "paper_sharpe_ratio": _decimal(report.paper_sharpe_ratio),
                "paper_total_return": _decimal(report.paper_total_return),
                "paper_trade_count": str(report.paper_trade_count),
            }.items()
        )
        parts.extend(f"{key}: {value}\n" for key, value in paper_rows)
    body = "".join(parts)
    body.encode("ascii")
    return body
