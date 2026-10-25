"""Holdout-aware single search entry point (BT-07).

After this module, `run_search` is the only search entry point: the retired
weight-and-threshold search module is gone, and nothing else in the engine
or backtest packages selects parameter sets.

Protocol (CONTEXT D-05, D-06, D-10 and G-05):

- The holdout is the final HOLDOUT_FRACTION of the dataset time span; no
  tuning step may read it.
- Tuning scores every candidate over walk-forward folds confined to the
  pre-holdout region and records each trial in the TrialLedger.
- The winning set is evaluated on the holdout exactly once, for the record
  only: the holdout score never feeds back into selection.
- Trial accounting follows the ledger rule: past MAX_ELIGIBLE_TRIALS the
  result flags ineligible for promotion; past MAX_ALLOWED_TRIALS recording
  raises TooManyTrialsError through this function.

Scoring is a deterministic digest of (seed, parameter-set hash, fold ids),
so identical inputs select the identical winner with no wall clock, no
network and no holdout reads during tuning. Scores are selection mechanics,
not performance claims: they carry no return, drawdown or forecast meaning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from pumpgrok.backtest.manifest import _resolve_dataset_dir
from pumpgrok.backtest.split import holdout_split, walk_forward_folds
from pumpgrok.backtest.trials import MAX_ELIGIBLE_TRIALS, TrialLedger
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.ids import IdFactory
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.replay.rng import make_rng

__all__ = [
    "HarnessResult",
    "ParamSpace",
    "run_search",
]

#: Candidate parameter sets to choose from. Each entry is one JSON-stable
#: mapping (ints, strings, bools, None, lists, dicts; float leaves are
#: rejected by canonical_json, so express ratios in basis points).
ParamSpace = Sequence[Mapping[str, Any]]

#: Scale mapping a 256-bit digest to a unit-interval score.
_DIGEST_SCALE = float(1 << 256)


@dataclass(frozen=True)
class HarnessResult:
    """Outcome of one holdout-aware search.

    best_params_hash is the sha256 of the winning set's canonical JSON.
    holdout_id names the holdout window the winner was evaluated on once.
    trial_count is the ledger size after this search recorded its trials.
    eligible_for_promotion is false when the ledger holds more than
    MAX_ELIGIBLE_TRIALS trials. holdout_score is the deterministic digest
    score of the winner on the holdout window, reported for completeness;
    it is a selection record, not a performance claim.
    """

    best_params_hash: str
    holdout_id: str
    trial_count: int
    eligible_for_promotion: bool
    holdout_score: float


def _load_stamps(dataset: str) -> tuple[float, ...]:
    """Epoch stamps of one recorded dataset in fixture order.

    Datasets resolve exactly like run manifests: a directory path or a
    fixture name under tests/fixtures/replay. No network, no wall clock.
    """
    directory = _resolve_dataset_dir(dataset)
    return tuple(event_epoch(event) for event in load_dataset(directory).events)


def _params_hash(params: Mapping[str, Any]) -> str:
    """sha256 over the canonical JSON of one candidate parameter set."""
    try:
        raw = canonical_json(params)
    except TypeError as err:
        raise ValueError(f"candidate parameter set is not JSON-stable: {err}") from err
    return sha256(raw.encode("utf-8")).hexdigest()


def _score_candidate(
    params_hash: str,
    seed: int,
    folds: tuple[tuple[str, str], ...],
    tuning_stamps: Sequence[float],
    cutoff: float,
) -> float:
    """Mean digest score of one candidate over the tuning folds.

    tuning_stamps must all sit below cutoff; a holdout stamp smuggled into
    tuning trips the assert instead of leaking into selection. Fold ids name
    pre-holdout windows only, so the digest reads no holdout data.
    """
    assert all(ts < cutoff for ts in tuning_stamps), "tuning observed a holdout stamp"
    assert folds, "need at least one tuning fold"
    total = 0.0
    for train_id, test_id in folds:
        digest = sha256(
            f"{seed}|{params_hash}|{train_id}|{test_id}|{len(tuning_stamps)}".encode()
        ).hexdigest()
        total += int(digest, 16) / _DIGEST_SCALE
    return total / len(folds)


def _evaluate_holdout(
    params_hash: str,
    seed: int,
    holdout_id: str,
    holdout_stamps: Sequence[float],
    cutoff: float,
) -> float:
    """Score the winning set on the holdout window, exactly once per search.

    Every stamp must sit at or above cutoff; a tuning stamp here means the
    windows were mixed up. The score is reported, never fed back into
    selection, so tuning cannot peek at the holdout through this call.
    """
    assert all(ts >= cutoff for ts in holdout_stamps), "holdout window is mixed up"
    assert holdout_stamps, "holdout window holds no stamps"
    digest = sha256(f"{seed}|{params_hash}|{holdout_id}|{len(holdout_stamps)}".encode()).hexdigest()
    return int(digest, 16) / _DIGEST_SCALE


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
) -> HarnessResult:
    """Tune over pre-holdout folds, then evaluate the winner on holdout once.

    dataset is a directory path or a recorded fixture name. space holds the
    candidate parameter sets; n_trials of them are drawn in seed order and
    every one is recorded in the TrialLedger, so n_trials past
    MAX_ALLOWED_TRIALS raises TooManyTrialsError and the fifty stored trials
    stay put. n_folds sets the walk-forward fold count over the pre-holdout
    region. run_id and ledger_path pin the ledger location (tests do); when
    omitted a fresh ULID names a new ledger under var/backtest.
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
    folds = walk_forward_folds(stamps, dataset, n_folds)
    ledger = TrialLedger(
        run_id=run_id if run_id is not None else _default_run_id(seed),
        path=ledger_path,
    )
    rng = make_rng(seed)
    order = list(range(len(candidates)))
    rng.shuffle(order)
    scored: list[tuple[float, str]] = []
    for position in order[:n_trials]:
        params_hash = _params_hash(candidates[position])
        ledger.record_trial(params_hash)
        scored.append(
            (_score_candidate(params_hash, seed, folds, tuning_stamps, cutoff), params_hash)
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    best_params_hash = scored[0][1]
    holdout_score = _evaluate_holdout(
        best_params_hash, seed, split.holdout_id, holdout_stamps, cutoff
    )
    eligible = all(verdict.eligible_for_promotion for verdict in ledger.trials)
    assert eligible == (len(ledger) <= MAX_ELIGIBLE_TRIALS), "ledger verdicts disagree"
    return HarnessResult(
        best_params_hash=best_params_hash,
        holdout_id=split.holdout_id,
        trial_count=len(ledger),
        eligible_for_promotion=eligible,
        holdout_score=holdout_score,
    )
