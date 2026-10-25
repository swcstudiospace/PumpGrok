"""Holdout split and walk-forward fold contracts (BT-03)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.backtest.split import (
    HOLDOUT_FRACTION,
    holdout_split,
    walk_forward_folds,
)
from pumpgrok.replay.fixtures import event_epoch, load_dataset

SMOKE_10M = Path(__file__).resolve().parents[1] / "fixtures" / "replay" / "smoke-10m"


def test_holdout_fraction_is_twenty_percent() -> None:
    assert HOLDOUT_FRACTION == 0.20


def test_holdout_covers_final_fifth_of_window_by_span() -> None:
    stamps = [float(t) for t in range(100)]
    split = holdout_split(stamps, "smoke")
    assert split.holdout_id == "smoke-holdout"
    assert split.train_end_ts == pytest.approx(99.0 - 0.20 * 99.0)
    assert split.holdout_start_ts == split.train_end_ts
    assert split.train_ids == tuple(f"smoke-train-{i}" for i in range(80))
    assert all(ts < split.holdout_start_ts for i, ts in enumerate(stamps) if i < 80)
    assert all(ts >= split.holdout_start_ts for i, ts in enumerate(stamps) if i >= 80)


def test_fold_test_regions_never_intersect_holdout() -> None:
    stamps = [float(t) for t in range(100)]
    split = holdout_split(stamps, "smoke")
    folds = walk_forward_folds(stamps, "smoke", 3)
    assert len(folds) == 3
    flat = [name for pair in folds for name in pair]
    assert split.holdout_id not in flat
    assert len(set(flat)) == len(flat)
    assert [train for train, _test in folds] == ["smoke-train-1", "smoke-train-2", "smoke-train-3"]
    assert [test for _train, test in folds] == ["smoke-test-1", "smoke-test-2", "smoke-test-3"]
    assert all(name.startswith("smoke-") for name in flat)


def test_split_identifiers_stable_for_identical_inputs() -> None:
    stamps = [float(t) for t in range(100)]
    assert holdout_split(stamps, "smoke") == holdout_split(list(stamps), "smoke")
    assert walk_forward_folds(stamps, "smoke", 3) == walk_forward_folds(list(stamps), "smoke", 3)


def test_smoke_10m_holdout_is_final_fifth_by_span() -> None:
    dataset = load_dataset(SMOKE_10M)
    stamps = [event_epoch(event) for event in dataset.events]
    split = holdout_split(stamps, "smoke-10m")
    low = min(stamps)
    high = max(stamps)
    assert split.holdout_start_ts == pytest.approx(high - HOLDOUT_FRACTION * (high - low))
    assert split.holdout_id == "smoke-10m-holdout"
    late = [ts for ts in stamps if ts >= split.holdout_start_ts]
    assert late
    assert len(split.train_ids) == len(stamps) - len(late)
    folds = walk_forward_folds(stamps, "smoke-10m", 3)
    assert len(folds) == 3
    flat = [name for pair in folds for name in pair]
    assert split.holdout_id not in flat


def test_empty_stamps_rejected() -> None:
    with pytest.raises(ValueError, match="at least one timestamp"):
        holdout_split([], "smoke")
    with pytest.raises(ValueError, match="at least one timestamp"):
        walk_forward_folds([], "smoke", 2)


def test_empty_dataset_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty name"):
        holdout_split([1.0, 2.0], "")


def test_zero_folds_rejected() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        walk_forward_folds([float(t) for t in range(100)], "smoke", 0)


def test_too_few_pre_holdout_stamps_rejected() -> None:
    with pytest.raises(ValueError, match="pre-holdout"):
        walk_forward_folds([0.0, 1.0], "smoke", 3)


def test_zero_span_window_puts_everything_in_holdout() -> None:
    split = holdout_split([5.0, 5.0], "smoke")
    assert split.train_ids == ()
    assert split.holdout_id == "smoke-holdout"
    assert split.holdout_start_ts == pytest.approx(5.0)
