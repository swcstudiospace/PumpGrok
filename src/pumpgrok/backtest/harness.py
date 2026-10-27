"""Holdout-aware single search entry point (BT-07).

After this module, `run_search` is the only search entry point: the retired
weight-and-threshold search module is gone, and nothing else in the engine
or backtest packages selects parameter sets.

Protocol (CONTEXT D-05, D-06, D-10 and G-05):

- The holdout is the final HOLDOUT_FRACTION of the dataset time span; no
  tuning step may read it.
- Tuning scores every candidate over walk-forward fold windows confined to
  the pre-holdout region and records each trial in the TrialLedger.
- The winning set is evaluated on the holdout exactly once, for the record
  only: the holdout result never feeds back into selection.
  The winner's holdout ledger is replayed once; holdout_ledger_path keeps it for the caller.
- Trial accounting follows the ledger rule: past MAX_ELIGIBLE_TRIALS the
  result flags ineligible for promotion; past MAX_ALLOWED_TRIALS recording
  raises TooManyTrialsError through this function.

Scoring is real replay (correction D-C3, D-C4): each candidate mapping is
validated by CandidateParams against the real FilterSettings and
ExitsSettings models, replayed through the real engine and PaperAdapter over
each pre-holdout fold window, and scored as the mean over the folds of each eval
ledger's net realized lamports: closing equity less opening equity, with open
positions at mark or else cost basis, the rule in equity.py. Every venue fee and
network cost sits in its cash movement and each refusal fee counts once; partial
fills count at their recorded filled amount; zero trades score 0. Candidates are
taken in space order with no shuffle and the best is tracked with strict
greater-than, so ties keep the earlier candidate. Scores are measured
returns over the replayed windows, never forecasts.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.backtest.evaluate import CandidateParams, evaluate_window, fold_windows
from pumpgrok.backtest.manifest import _resolve_dataset_dir
from pumpgrok.backtest.split import holdout_split
from pumpgrok.backtest.trials import MAX_ELIGIBLE_TRIALS, TrialLedger
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.limits import EngineLimits

__all__ = [
    "HarnessResult",
    "ParamSpace",
    "run_search",
]

#: Candidate parameter sets to choose from. Each entry is one JSON-stable
#: mapping (ints, strings, bools, None, lists, dicts; float leaves are
#: rejected by canonical_json, so accepted knobs are ints and bools only)
#: holding optional `filter` and `exits` override subsets validated by
#: CandidateParams against the real settings models.
ParamSpace = Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class HarnessResult:
    """Outcome of one holdout-aware search.

    best_params_hash is the parameter-set identity hash of the winning
    set (CandidateParams.content_hash, which ParamSet.content_hash also reports).
    holdout_id names the
    holdout window the winner was evaluated on once. trial_count is the
    ledger size after this search recorded its trials.
    eligible_for_promotion is false when the ledger holds more than
    MAX_ELIGIBLE_TRIALS trials. best_net_lamports is the mean net
    realized lamports of the winner over the tuning folds;
    holdout_net_lamports is the net realized lamports of the winner on
    the holdout window, reported for completeness and never fed back
    into selection. Both are measured returns, not performance claims.
    """

    best_params_hash: str
    holdout_id: str
    trial_count: int
    eligible_for_promotion: bool
    holdout_net_lamports: int
    best_net_lamports: int


def _load_stamps(dataset: str) -> tuple[float, ...]:
    """Epoch stamps of one recorded dataset in fixture order.

    Datasets resolve exactly like run manifests: a directory path or a
    fixture name under tests/fixtures/replay. No network, no wall clock.
    """
    directory = _resolve_dataset_dir(dataset)
    return tuple(event_epoch(event) for event in load_dataset(directory).events)


def _default_run_id(seed: int) -> str:
    """Fresh ULID for the ledger directory of a search without a caller id."""
    return IdFactory(WallClock(), make_rng(seed)).ulid()


def run_search(
    dataset: str,
    space: ParamSpace,
    n_trials: int,
    seed: int,
    *,
    n_folds: int = 3,
    run_id: str | None = None,
    ledger_path: Path | None = None,
    risk_budget: RiskBudget | None = None,
    limits: EngineLimits | None = None,
    holdout_ledger_path: Path | None = None,
) -> HarnessResult:
    """Tune over pre-holdout folds, then evaluate the winner on holdout once.

    dataset is a directory path or a recorded fixture name. space holds the
    candidate parameter sets; n_trials of them are taken in space order and
    every one is recorded in the TrialLedger, so n_trials past
    MAX_ALLOWED_TRIALS raises TooManyTrialsError and the fifty stored trials
    stay put. n_folds sets the walk-forward fold count over the pre-holdout
    region. run_id and ledger_path pin the ledger location (tests do); when
    omitted a fresh ULID names a new ledger under var/backtest. seed drives
    replay determinism inside each window evaluation. Each candidate is
    validated by CandidateParams before it is recorded, so unknown keys and
    scoring knobs fail closed with a validation error.
    risk_budget and limits reach every window replay unchanged; omitted means the
    replay defaults. holdout_ledger_path, when given, keeps the winner's holdout
    ledger at that path so the caller reads its rows without a second replay.
    """
    if not dataset:
        raise ValueError("dataset must be a non-empty path or fixture name")
    candidates = list(space)
    if n_trials < 1:
        raise ValueError(f"n_trials must be at least 1, found {n_trials}")
    if n_trials > len(candidates):
        raise ValueError(f"n_trials {n_trials} passes the {len(candidates)} candidates in space")
    stamps = _load_stamps(dataset)
    split = holdout_split(stamps, dataset)
    cutoff = split.holdout_start_ts
    tuning_stamps = tuple(ts for ts in stamps if ts < cutoff)
    holdout_stamps = tuple(ts for ts in stamps if ts >= cutoff)
    assert len(tuning_stamps) + len(holdout_stamps) == len(stamps), (
        "tuning and holdout must partition the dataset"
    )
    assert all(ts < cutoff for ts in tuning_stamps), "tuning read the holdout window"
    windows = fold_windows(stamps, dataset, n_folds)
    ledger = TrialLedger(
        run_id=run_id if run_id is not None else _default_run_id(seed),
        path=ledger_path,
    )
    best_params_hash = ""
    best_params: CandidateParams | None = None
    best_mean = 0
    with tempfile.TemporaryDirectory(prefix="pumpgrok-search-") as scratch:
        scratch_path = Path(scratch)
        for position in range(n_trials):
            mapping = candidates[position]
            try:
                canonical_json(mapping)
            except TypeError as err:
                raise ValueError(f"candidate parameter set is not JSON-stable: {err}") from err
            params = CandidateParams(**dict(mapping))
            params_hash = params.content_hash
            ledger.record_trial(params_hash)
            total = 0
            for fold_index, window in enumerate(windows.folds):
                assert window.end_ts <= cutoff, "tuning observed a holdout stamp"
                total += evaluate_window(
                    dataset,
                    params,
                    seed=seed,
                    ledger_path=scratch_path / f"trial-{position}-fold-{fold_index}.sqlite",
                    window=window,
                    risk_budget=risk_budget,
                    limits=limits,
                )
            mean = total // len(windows.folds)
            if best_params is None or mean > best_mean:
                best_mean = mean
                best_params_hash = params_hash
                best_params = params
        assert best_params is not None, "need at least one scored candidate"
        assert all(ts >= cutoff for ts in holdout_stamps), "holdout window is mixed up"
        if holdout_ledger_path is None:
            holdout_path = scratch_path / "holdout.sqlite"
        else:
            holdout_path = Path(holdout_ledger_path)
            holdout_path.parent.mkdir(parents=True, exist_ok=True)
        holdout_net = evaluate_window(
            dataset,
            best_params,
            seed=seed,
            ledger_path=holdout_path,
            window=windows.holdout,
            risk_budget=risk_budget,
            limits=limits,
        )
    eligible = all(verdict.eligible_for_promotion for verdict in ledger.trials)
    assert eligible == (len(ledger) <= MAX_ELIGIBLE_TRIALS), "ledger verdicts disagree"
    return HarnessResult(
        best_params_hash=best_params_hash,
        holdout_id=split.holdout_id,
        trial_count=len(ledger),
        eligible_for_promotion=eligible,
        holdout_net_lamports=holdout_net,
        best_net_lamports=best_mean,
    )
