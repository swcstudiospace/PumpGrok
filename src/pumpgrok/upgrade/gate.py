"""Promotion gate (UPG-02; CONTEXT D-05, G-08).

evaluate_candidate runs the five checks in gate order bounds, then trials,
then autonomy level, then holdout, then divergence, where the first failure
wins as the typed reason and a pass returns promotion_eligible true. The
gate reuses the Phase 8 divergence check with its D7 defaults on the same
window, the trial ledger counts with the 20 and 50 limits, read_autonomy
for the level, and the harness holdout result; it invents no second search
engine and no new threshold. An out-of-bounds candidate, a failed holdout,
a divergence breach, a search above 20 trials, or a run below the
autonomous-paper level each blocks promotion.

Money never appears here: the holdout rule reads the measured net realized
lamports sign only, and no hash, random value, or digest acts as a score, a
metric, or a verdict. Hashes name exact sets and runs; they never decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pumpgrok.backtest.divergence import breach_line, check
from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.upgrade.bounds import Bounds, OutOfBoundsError, validate_against_bounds
from pumpgrok.upgrade.params import ParamSet

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "REASON_BELOW_AUTONOMY_LEVEL",
    "REASON_DIVERGENCE_BREACH",
    "REASON_HOLDOUT_FAILED",
    "REASON_OUT_OF_BOUNDS",
    "REASON_PASS",
    "REASON_TOO_MANY_TRIALS",
    "REQUIRED_AUTONOMY_LEVEL",
    "GateReason",
    "GateVerdict",
    "evaluate_candidate",
]

#: Reason vocabulary for GateVerdict.reason. "pass" is the only eligible
#: reason; every other value names the first gate check that failed.
GateReason = Literal[
    "pass",
    "out_of_bounds",
    "too_many_trials",
    "below_autonomy_level",
    "holdout_failed",
    "divergence_breach",
]

REASON_PASS: GateReason = "pass"  # noqa: S105 - gate reason code, not a credential
REASON_OUT_OF_BOUNDS: GateReason = "out_of_bounds"
REASON_TOO_MANY_TRIALS: GateReason = "too_many_trials"
REASON_BELOW_AUTONOMY_LEVEL: GateReason = "below_autonomy_level"
REASON_HOLDOUT_FAILED: GateReason = "holdout_failed"
REASON_DIVERGENCE_BREACH: GateReason = "divergence_breach"

#: The autonomy level a promotion requires (risk engine precedent: only
#: autonomous-paper mints autonomous approvals; manual-ticket never upgrades).
REQUIRED_AUTONOMY_LEVEL = "autonomous-paper"


@dataclass(frozen=True)
class GateVerdict:
    """Outcome of one promotion-gate evaluation.

    promotion_eligible is true only when every check passes. reason is the
    typed cause: "pass", or the first failing check in gate order. detail
    carries the human-readable cause and never a score.
    """

    promotion_eligible: bool
    reason: GateReason
    detail: str


def evaluate_candidate(
    params: ParamSet,
    *,
    bounds: Bounds,
    search: HarnessResult,
    run_id: str,
    store: LedgerStore,
    backtest: MetricsReport,
    paper: MetricsReport,
) -> GateVerdict:
    """Run the five gate checks in order; first failure wins as the reason.

    params is the candidate set; search is the harness holdout result for
    the winning set (trial counts and the once-only holdout net); run_id is
    the backtest run id the evidence will record; store supplies the
    autonomy level through read_autonomy; backtest and paper are same-window
    summaries the divergence check compares with its D7 defaults.

    The candidate must be the search winner: a params hash that does not
    match search.best_params_hash raises ValueError instead of a verdict,
    so no candidate can promote on another set's holdout. A pass returns
    promotion_eligible true with reason "pass".
    """
    if not run_id:
        raise ValueError("run_id must be a non-empty backtest run id")
    if params.content_hash != search.best_params_hash:
        raise ValueError(
            "candidate hash does not match the search winner: "
            "gate inputs must describe one candidate"
        )
    if search.trial_count < 1:
        raise ValueError(f"trial_count must be at least 1, found {search.trial_count}")
    try:
        validate_against_bounds(params, bounds)
    except OutOfBoundsError as err:
        return GateVerdict(
            promotion_eligible=False,
            reason=REASON_OUT_OF_BOUNDS,
            detail=str(err),
        )
    if (
        search.trial_count > MAX_ELIGIBLE_TRIALS
        or search.trial_count > MAX_ALLOWED_TRIALS
        or not search.eligible_for_promotion
    ):
        return GateVerdict(
            promotion_eligible=False,
            reason=REASON_TOO_MANY_TRIALS,
            detail=(
                f"trial_count {search.trial_count} passes the "
                f"{MAX_ELIGIBLE_TRIALS} eligible-trial limit "
                f"(ledger refuses past {MAX_ALLOWED_TRIALS})"
            ),
        )
    level = read_autonomy(store)
    if level != REQUIRED_AUTONOMY_LEVEL:
        return GateVerdict(
            promotion_eligible=False,
            reason=REASON_BELOW_AUTONOMY_LEVEL,
            detail=(
                f"autonomy level {level!r} is below the required "
                f"{REQUIRED_AUTONOMY_LEVEL!r}; manual-ticket never upgrades"
            ),
        )
    if search.holdout_net_lamports <= 0:
        return GateVerdict(
            promotion_eligible=False,
            reason=REASON_HOLDOUT_FAILED,
            detail=(
                f"holdout {search.holdout_id} net "
                f"{search.holdout_net_lamports} lamports shows no measured "
                "edge on the unseen window"
            ),
        )
    verdict = check(backtest, paper)
    if verdict.blocks_promotion:
        return GateVerdict(
            promotion_eligible=False,
            reason=REASON_DIVERGENCE_BREACH,
            detail=breach_line(verdict) or "divergence blocks promotion",
        )
    return GateVerdict(
        promotion_eligible=True,
        reason=REASON_PASS,
        detail=(
            f"candidate {params.content_hash} eligible via run {run_id} holdout {search.holdout_id}"
        ),
    )
