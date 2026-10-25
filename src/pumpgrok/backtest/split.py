"""Holdout split and walk-forward folds (BT-03; CONTEXT D-05 and G-05).

The holdout is the final HOLDOUT_FRACTION of the time window measured by
timestamp span, never by event count. Tuning folds live in the pre-holdout
region only; no tuning step may read the holdout. Every function here is pure:
it reads time only through the passed-in stamp sequence, never the wall clock,
and performs no I/O and no randomness.

Identifier patterns (stable for identical inputs; DATASET is the
caller-supplied dataset name):
- pre-holdout stamp at input index I: DATASET-train-I
- holdout region: DATASET-holdout
- walk-forward fold K, 1-based: train DATASET-train-K, test DATASET-test-K

Fold train ids reuse the DATASET-train-N pattern with N as the 1-based fold
number; per-stamp train ids use the input index instead. A fold train id names
the cumulative training set of that round, not one stamp.

Fold geometry: the pre-holdout stamps keep their input order and are cut into
N + 1 contiguous blocks for N folds; fold K trains on blocks 1 through K and
tests on block K + 1. Block boundary J lands at index (J * M) // (N + 1) for a
pre-holdout count M, so every fold has a non-empty train and test and the
union of the test blocks is exactly the pre-holdout region.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

HOLDOUT_FRACTION = 0.20


@dataclass(frozen=True)
class HoldoutSplit:
    """Named split of one dataset window into a train region and a holdout.

    train_end_ts and holdout_start_ts are the same single cutoff: stamps below
    it are train, stamps at or above it are holdout. A zero-span window (every
    stamp identical) puts every stamp in the holdout and leaves train empty.
    """

    dataset: str
    train_ids: tuple[str, ...]
    holdout_id: str
    train_end_ts: float
    holdout_start_ts: float


def _require_dataset(dataset: str) -> None:
    if not dataset:
        raise ValueError("dataset must be a non-empty name")


def _cutoff_ts(stamps: Sequence[float]) -> float:
    if len(stamps) == 0:
        raise ValueError("stamps must hold at least one timestamp")
    low = min(stamps)
    high = max(stamps)
    return high - HOLDOUT_FRACTION * (high - low)


def holdout_split(stamps: Sequence[float], dataset: str) -> HoldoutSplit:
    """Split stamps into a train region and the final-fifth holdout.

    The holdout covers the final HOLDOUT_FRACTION of the timestamp span; the
    train region is every stamp below the cutoff. Identifiers are stable for
    identical inputs.
    """
    _require_dataset(dataset)
    cutoff = _cutoff_ts(stamps)
    train_ids = tuple(f"{dataset}-train-{i}" for i, ts in enumerate(stamps) if ts < cutoff)
    return HoldoutSplit(
        dataset=dataset,
        train_ids=train_ids,
        holdout_id=f"{dataset}-holdout",
        train_end_ts=cutoff,
        holdout_start_ts=cutoff,
    )


def walk_forward_folds(
    stamps: Sequence[float], dataset: str, n_folds: int
) -> tuple[tuple[str, str], ...]:
    """Return N expanding-window (train, test) id pairs over pre-holdout stamps.

    Every pair is confined to the pre-holdout region, so no fold test region
    ever intersects the holdout. Fold trains expand: fold K trains on blocks 1
    through K and tests on block K + 1 under the geometry in the module
    docstring. Requires at least N + 1 pre-holdout stamps.
    """
    _require_dataset(dataset)
    if n_folds < 1:
        raise ValueError("n_folds must be at least 1")
    cutoff = _cutoff_ts(stamps)
    pre_count = sum(1 for ts in stamps if ts < cutoff)
    if pre_count < n_folds + 1:
        msg = f"need at least {n_folds + 1} pre-holdout stamps for {n_folds} folds"
        raise ValueError(f"{msg}, found {pre_count}")
    return tuple((f"{dataset}-train-{k}", f"{dataset}-test-{k}") for k in range(1, n_folds + 1))
