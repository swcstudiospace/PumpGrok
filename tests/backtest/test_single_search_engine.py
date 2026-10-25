"""Single search engine contract (BT-07; criterion 8).

The holdout-aware harness is the only importable search entry point:
tuning never observes holdout stamps, above-20-trial searches flag
ineligible, and above-50-trial searches raise the typed error through
the harness. Scores are real replay lamports observed through
evaluate_window calls, never digests.
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
from pumpgrok.backtest.evaluate import CandidateParams, EvalWindow
from pumpgrok.backtest.harness import HarnessResult, run_search
from pumpgrok.backtest.manifest import param_set_hash
from pumpgrok.backtest.split import holdout_split
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS, TooManyTrialsError
from pumpgrok.core.idempotency import canonical_json


def _space(count: int) -> list[dict[str, Any]]:
    """Count distinct valid candidate parameter sets (filter overrides)."""
    return [{"filter": {"min_unique_buyers": 5 + i}} for i in range(count)]


def _identity_hash(candidate: dict[str, Any]) -> str:
    """Parameter-set identity hash the harness records for one candidate."""
    return param_set_hash(canonical_json(candidate).encode("utf-8"))


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


def test_small_search_stays_eligible(tmp_path: Path) -> None:
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
    assert isinstance(result.best_net_lamports, int)
    assert isinstance(result.holdout_net_lamports, int)


def test_tuning_never_observes_holdout_stamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamps = harness._load_stamps("smoke")
    split = holdout_split(stamps, "smoke")
    cutoff = split.holdout_start_ts
    holdout_stamps = tuple(ts for ts in stamps if ts >= cutoff)
    assert holdout_stamps, "smoke must hold stamps past the cutoff"
    tuning_ids: list[str] = []
    holdout_ids: list[str] = []
    tuning_ranges: list[tuple[float, float]] = []
    real_evaluate = harness.evaluate_window

    def spy(
        dataset: str | Path,
        params: CandidateParams,
        *,
        seed: int,
        ledger_path: str | Path,
        window: EvalWindow,
    ) -> int:
        if window.window_id == split.holdout_id:
            holdout_ids.append(window.window_id)
        else:
            tuning_ids.append(window.window_id)
            tuning_ranges.append((window.start_ts, window.end_ts))
        return real_evaluate(dataset, params, seed=seed, ledger_path=ledger_path, window=window)

    monkeypatch.setattr(harness, "evaluate_window", spy)
    result = run_search(
        "smoke",
        _space(5),
        5,
        7,
        run_id="PROBE01",
        ledger_path=tmp_path / "trials.jsonl",
    )
    assert tuning_ids, "tuning must score candidates over tuning folds"
    for start_ts, end_ts in tuning_ranges:
        assert end_ts <= cutoff, "tuning window reached past the cutoff"
        assert not any(start_ts <= ts < end_ts for ts in holdout_stamps)
    assert len(holdout_ids) == 1, "the winner is evaluated on holdout exactly once"
    assert holdout_ids[0] == result.holdout_id == "smoke-holdout"


def test_above_20_trials_flags_ineligible(tmp_path: Path) -> None:
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


def test_above_50_trials_raises_typed_error(tmp_path: Path) -> None:
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


def test_identical_inputs_select_the_identical_winner(tmp_path: Path) -> None:
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
    assert isinstance(first.best_net_lamports, int)
    assert isinstance(first.holdout_net_lamports, int)


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
    assert result.best_net_lamports == 0
    assert result.holdout_net_lamports == 0


def test_all_zero_candidate_space_keeps_first_by_order(tmp_path: Path) -> None:
    space = _space(3)
    result = run_search(
        "smoke-10m",
        space,
        3,
        11,
        run_id="ZERO01",
        ledger_path=tmp_path / "a.jsonl",
    )
    assert result.best_net_lamports == 0
    assert result.best_params_hash == _identity_hash(space[0])
    flipped = list(reversed(space))
    rerun = run_search(
        "smoke-10m",
        flipped,
        3,
        11,
        run_id="ZERO02",
        ledger_path=tmp_path / "b.jsonl",
    )
    assert rerun.best_net_lamports == 0
    assert rerun.best_params_hash == _identity_hash(flipped[0])
    assert rerun.best_params_hash != result.best_params_hash


def test_bad_counts_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        run_search("smoke", _space(3), 0, 1, ledger_path=tmp_path / "a.jsonl")
    with pytest.raises(ValueError, match="passes the 2 candidates"):
        run_search("smoke", _space(2), 3, 1, ledger_path=tmp_path / "b.jsonl")
    with pytest.raises(ValueError, match="non-empty"):
        run_search("", _space(2), 1, 1, ledger_path=tmp_path / "c.jsonl")


def test_float_candidate_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="JSON-stable"):
        run_search(
            "smoke",
            [{"ratio": 0.5}],
            1,
            1,
            run_id="FLOAT01",
            ledger_path=tmp_path / "trials.jsonl",
        )
