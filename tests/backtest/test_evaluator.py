"""Window evaluator on the recorded fixtures (BT-03, BT-07).

Desk-default overrides score the smoke full window as the ledger-derived
net recorded cash change: the sum of FillRecorded cash_delta_lamports (every
venue fee and network cost already inside it) minus the sum of OrderRejected
fees_lamports, identical across runs, with no sign assumption.
Every smoke-10m window scores an honest zero with no fills. Unknown keys
and scoring-only knobs raise validation errors. Offline only, tmp ledgers
under tmp_path, no network, no wall clock.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pumpgrok.backtest.evaluate import (
    CandidateParams,
    EvalWindow,
    ScoringKnobError,
    _reject_scoring_knobs,
    evaluate_window,
    fold_windows,
)
from pumpgrok.config.settings import FilterSettings
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.supervisor.scheduler import run_once_replay

REPO = Path(__file__).resolve().parents[2]
SMOKE = REPO / "tests" / "fixtures" / "replay" / "smoke"
SMOKE_10M = REPO / "tests" / "fixtures" / "replay" / "smoke-10m"
SEED = 20260101


def _stamps(dataset_dir: Path) -> tuple[float, ...]:
    """Epoch stamps of one fixture in file order."""
    return tuple(event_epoch(event) for event in load_dataset(dataset_dir).events)


def _full_window(dataset_dir: Path, window_id: str) -> EvalWindow:
    """Window covering every stamp of one fixture."""
    stamps = _stamps(dataset_dir)
    return EvalWindow(window_id=window_id, start_ts=min(stamps), end_ts=float("inf"))


def _ledger_math(ledger_path: Path) -> tuple[int, int]:
    """Independent net lamports and fill count from one ledger's fills."""
    store = LedgerStore(ledger_path)
    try:
        fills = store.read(types=["FillRecorded"], limit=None)
        rejections = store.read(types=["OrderRejected"], limit=None)
    finally:
        store.close()
    cash_total = 0
    for row in fills:
        payload = row["payload"]
        assert isinstance(payload, dict)
        cash_total += int(payload["cash_delta_lamports"])
    for row in rejections:
        payload = row["payload"]
        assert isinstance(payload, dict)
        cash_total -= int(payload["fees_lamports"])
    return cash_total, len(fills)


def test_desk_defaults_score_matches_ledger_math(tmp_path: Path) -> None:
    """Smoke full-window score equals the ledger-derived net lamports."""
    window = _full_window(SMOKE, "smoke-full")
    score = evaluate_window(
        "smoke",
        CandidateParams(),
        seed=SEED,
        ledger_path=tmp_path / "eval.sqlite",
        window=window,
    )
    assert isinstance(score, int)
    assert not isinstance(score, bool)
    reference = run_once_replay(
        SMOKE, FilterSettings(), seed=SEED, ledger_path=tmp_path / "ref.sqlite"
    )
    assert reference.trades, "the smoke replay must place at least one order"
    expected, fill_count = _ledger_math(tmp_path / "ref.sqlite")
    assert fill_count > 0
    assert score == expected


def test_identical_inputs_give_identical_scores(tmp_path: Path) -> None:
    """Two runs over the same window and overrides agree exactly."""
    window = _full_window(SMOKE, "smoke-full")
    first = evaluate_window(
        "smoke",
        CandidateParams(),
        seed=SEED,
        ledger_path=tmp_path / "first.sqlite",
        window=window,
    )
    second = evaluate_window(
        "smoke",
        CandidateParams(),
        seed=SEED,
        ledger_path=tmp_path / "second.sqlite",
        window=window,
    )
    assert first == second


def test_smoke_10m_windows_score_honest_zero(tmp_path: Path) -> None:
    """Every smoke-10m window scores 0 with no fills, never an error."""
    stamps = _stamps(SMOKE_10M)
    windows = fold_windows(stamps, "smoke-10m", 2)
    assert [fold.window_id for fold in windows.folds] == ["smoke-10m-test-1", "smoke-10m-test-2"]
    assert windows.holdout.window_id == "smoke-10m-holdout"
    for position, window in enumerate((*windows.folds, windows.holdout)):
        score = evaluate_window(
            "smoke-10m",
            CandidateParams(),
            seed=SEED,
            ledger_path=tmp_path / f"quiet-{position}.sqlite",
            window=window,
        )
        assert score == 0
        _, fill_count = _ledger_math(tmp_path / f"quiet-{position}.sqlite")
        assert fill_count == 0


def test_relaxed_metadata_still_scores_zero_on_smoke_10m(tmp_path: Path) -> None:
    """require_metadata false changes nothing: None buyers fail closed."""
    window = _full_window(SMOKE_10M, "smoke-10m-full")
    score = evaluate_window(
        "smoke-10m",
        CandidateParams(filter={"require_metadata": False}),
        seed=SEED,
        ledger_path=tmp_path / "relaxed.sqlite",
        window=window,
    )
    assert score == 0


def test_unknown_top_level_key_raises_validation_error() -> None:
    """A scoring section beside filter and exits is rejected."""
    with pytest.raises(ValidationError):
        CandidateParams(**{"scoring": {"weights": {"audit": 0.5}}})


def test_unknown_nested_key_raises_validation_error() -> None:
    """An unknown field inside filter fails against FilterSettings."""
    with pytest.raises(ValidationError):
        CandidateParams(filter={"no_such_gate": True})


def test_scoring_knob_rejected_with_typed_error() -> None:
    """min_total_score is inert in replay and never tunable."""
    with pytest.raises(ScoringKnobError, match="scoring knob"):
        _reject_scoring_knobs("filter", {"min_total_score": 0.5})
    with pytest.raises(ValidationError, match="scoring knob"):
        CandidateParams(filter={"min_total_score": 0.5})
