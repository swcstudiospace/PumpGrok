"""Deterministic backtest Markdown report (BT-06; CONTEXT D-09 and G-01).

`render` produces byte-identical Markdown for identical inputs: sorted
keys, fixed integer formatting, no floats, and no wall-clock timestamps.
The report names the holdout id, the trial count, and the slippage and fee
figures the acceptance greps look for. Money stays integer base units;
Decimal appears nowhere; every figure describes the recorded evaluation,
never a forecast.

The single-parameter digest evaluation places no orders, so realized
slippage and fee totals are zero by construction. The Slippage and Fees
sections state the per-fill accounting and the desk schedule that apply
when the promotion gate runs the same window live on paper.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from pumpgrok.backtest.divergence import DivergenceVerdict

__all__ = [
    "BacktestReport",
    "render",
    "with_divergence",
]


@dataclass(frozen=True)
class BacktestReport:
    """Pure data for one backtest report: no I/O, built by the CLI verb.

    run_id derives from the run manifest; dataset names the recorded
    fixture; digests and hashes identify exact inputs. holdout_id names
    the holdout window; holdout_events and tuning_events count recorded
    ticks on each side of the cutoff. trial_count is the ledger size after
    this run recorded its trial. Fee fields quote the desk schedule from
    `execution.fees`; realized totals are zero because the digest
    evaluation places no orders. promotion_eligible follows trial
    eligibility until a divergence verdict clears it via with_divergence.
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
    holdout_rows = sorted(
        {
            "holdout_events": str(report.holdout_events),
            "holdout_id": report.holdout_id,
            "tuning_events": str(report.tuning_events),
        }.items()
    )
    trial_rows = sorted(
        {
            "eligible_for_promotion": _bool(report.eligible_for_promotion),
            "max_allowed_trials": str(report.max_allowed_trials),
            "max_eligible_trials": str(report.max_eligible_trials),
            "trial_count": str(report.trial_count),
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
    parts.append("## Holdout\n")
    parts.extend(f"{key}: {value}\n" for key, value in holdout_rows)
    parts.append("## Trials\n")
    parts.extend(f"{key}: {value}\n" for key, value in trial_rows)
    parts.append("## Slippage\n")
    parts.append(f"realized_slippage_bps_total: {report.realized_slippage_bps_total}\n")
    parts.append(
        "note: digest evaluation places no orders, so realized slippage is zero; "
        "per-fill realized_slippage_bps accounting applies at promotion\n"
    )
    parts.append("## Fees\n")
    parts.extend(f"{key}: {value}\n" for key, value in fee_rows)
    parts.append("## Verdict\n")
    parts.append(f"promotion_eligible: {_bool(report.promotion_eligible)}\n")
    parts.append(
        "divergence: not-compared (single-parameter backtest; "
        "the promotion gate compares the paper window)\n"
    )
    body = "".join(parts)
    body.encode("ascii")
    return body
