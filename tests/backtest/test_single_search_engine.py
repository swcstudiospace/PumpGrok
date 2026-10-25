"""Single search engine contract (BT-07; criterion 8).

The holdout-aware harness is the only importable search entry point:
tuning never observes holdout stamps, above-20-trial searches flag
ineligible, and above-50-trial searches raise the typed error through
the harness.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.backtest
import pumpgrok.engine
from pumpgrok.backtest import harness
from pumpgrok.backtest.harness import HarnessResult, run_search
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS, TooManyTrialsError


def _space(count: int) -> list[dict[str, Any]]:
    """Count distinct JSON-stable candidate parameter sets."""
    return [{"level_bp": 100 + i, "window": 5 + (i % 3)} for i in range(count)]


def _stamps(count: int = 100) -> tuple[float, ...]:
    """Evenly spaced synthetic stamps with a clean pre-holdout region."""
    return tuple(float(i) for i in range(count))


def test_run_search_is_the_only_search_entry_point() -> None:
    assert callable(run_search)
    assert run_search.__annotations__["space"] == "ParamSpace"
    for package in (pumpgrok.backtest, pumpgrok.engine):
        root = Path(str(package.__file__)).parent
        assert root.is_dir()
        for path in sorted(root.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if path.name == "harness.py":
                assert text.count("def run_search") == 1
            else:
                assert "def run_search" not in text, f"second search entry in {path}"
            assert "def simplex" not in text, f"retired helper in {path}"
            assert "def grid_lines" not in text, f"retired helper in {path}"
            assert "itertools.product" not in text, f"retired product in {path}"
    with pytest.raises(ImportError):
        importlib.import_module("pumpgrok.engine.tune")


def test_run_search_signature_matches_contract() -> None:
    params = list(inspect.signature(run_search).parameters)
    assert params[:4] == ["dataset", "space", "n_trials", "seed"]


def test_small_search_stays_eligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    result = run_search(
        "smoke",
        _space(5),
        5,
        11,
        run_id="ELIG01",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert isinstance(result, HarnessResult)
    assert result.holdout_id == "smoke-holdout"
    assert result.trial_count == 5
    assert result.eligible_for_promotion is True
    assert 0.0 <= result.holdout_score < 1.0


def test_tuning_never_observes_holdout_stamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = 1.0e15
    stamps = tuple(float(i) for i in range(80)) + (sentinel,) * 20
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: stamps)
    seen: list[tuple[float, ...]] = []
    real_score = harness._score_candidate

    def spy(
        params_hash: str,
        seed: int,
        folds: tuple[tuple[str, str], ...],
        tuning_stamps: Any,
        cutoff: float,
    ) -> float:
        seen.append(tuple(tuning_stamps))
        return real_score(params_hash, seed, folds, tuning_stamps, cutoff)

    holdout_calls: list[tuple[str, tuple[float, ...]]] = []
    real_holdout = harness._evaluate_holdout

    def holdout_spy(
        params_hash: str,
        seed: int,
        holdout_id: str,
        holdout_stamps: Any,
        cutoff: float,
    ) -> float:
        holdout_calls.append((holdout_id, tuple(holdout_stamps)))
        return real_holdout(params_hash, seed, holdout_id, holdout_stamps, cutoff)

    monkeypatch.setattr(harness, "_score_candidate", spy)
    monkeypatch.setattr(harness, "_evaluate_holdout", holdout_spy)
    result = run_search(
        "smoke",
        _space(5),
        5,
        7,
        run_id="PROBE01",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert seen, "tuning must score candidates over tuning folds"
    assert all(sentinel not in batch for batch in seen)
    assert all(len(batch) == 80 for batch in seen)
    assert len(holdout_calls) == 1, "the winner is evaluated on holdout exactly once"
    assert holdout_calls[0][0] == result.holdout_id == "smoke-holdout"
    assert sentinel in holdout_calls[0][1]


def test_above_20_trials_flags_ineligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    result = run_search(
        "smoke",
        _space(MAX_ELIGIBLE_TRIALS + 1),
        MAX_ELIGIBLE_TRIALS + 1,
        3,
        run_id="INELIG01",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert result.trial_count == MAX_ELIGIBLE_TRIALS + 1
    assert result.eligible_for_promotion is False


def test_above_50_trials_raises_typed_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    path = tmp_path / "trials.jsonl"
    with pytest.raises(TooManyTrialsError, match="51"):
        run_search(
            "smoke",
            _space(MAX_ALLOWED_TRIALS + 1),
            MAX_ALLOWED_TRIALS + 1,
            5,
            run_id="REJECT01",
            ledger_path=path,
        )
    assert len(path.read_text(encoding="utf-8").splitlines()) == MAX_ALLOWED_TRIALS


def test_identical_inputs_select_the_identical_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    first = run_search(
        "smoke",
        _space(8),
        8,
        9,
        run_id="DET01",
        ledger_path=tmp_path / "a.jsonl",
    )
    second = run_search(
        "smoke",
        _space(8),
        8,
        9,
        run_id="DET02",
        ledger_path=tmp_path / "b.jsonl",
    )
    assert first == second


def test_recorded_fixture_search_end_to_end(tmp_path: Path) -> None:
    result = run_search(
        "smoke-10m",
        _space(3),
        3,
        11,
        run_id="SMOKE01",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert result.holdout_id == "smoke-10m-holdout"
    assert result.trial_count == 3
    assert result.eligible_for_promotion is True


def test_bad_counts_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    with pytest.raises(ValueError, match="at least 1"):
        run_search("smoke", _space(3), 0, 1, ledger_path=tmp_path / "a.jsonl")
    with pytest.raises(ValueError, match="passes the 2 candidates"):
        run_search("smoke", _space(2), 3, 1, ledger_path=tmp_path / "b.jsonl")
    with pytest.raises(ValueError, match="non-empty"):
        run_search("", _space(2), 1, 1, ledger_path=tmp_path / "c.jsonl")


def test_float_candidate_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness, "_load_stamps", lambda dataset: _stamps())
    with pytest.raises(ValueError, match="JSON-stable"):
        run_search(
            "smoke",
            [{"ratio": 0.5}],
            1,
            1,
            run_id="FLOAT01",
            ledger_path=tmp_path / "trials.jsonl",
        )
