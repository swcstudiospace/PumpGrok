"""Trial ledger eligibility and rejection contracts (BT-04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.backtest.trials import (
    MAX_ALLOWED_TRIALS,
    MAX_ELIGIBLE_TRIALS,
    TooManyTrialsError,
    TrialLedger,
)
from pumpgrok.core.errors import PumpgrokError


def _record_many(ledger: TrialLedger, count: int) -> None:
    for i in range(1, count + 1):
        ledger.record_trial(f"params-hash-{i:03d}")


def test_trial_limits_match_contract() -> None:
    assert MAX_ELIGIBLE_TRIALS == 20
    assert MAX_ALLOWED_TRIALS == 50


def test_rejection_is_a_typed_pumpgrok_error() -> None:
    assert issubclass(TooManyTrialsError, PumpgrokError)
    assert TooManyTrialsError.code == "too_many_trials"


def test_trial_21_flags_ineligible_for_promotion(tmp_path: Path) -> None:
    ledger = TrialLedger(run_id="RUNID01", path=tmp_path / "trials.jsonl")
    verdicts = [ledger.record_trial(f"params-hash-{i:03d}") for i in range(1, 22)]
    assert [v.trial_number for v in verdicts] == list(range(1, 22))
    assert all(v.eligible_for_promotion for v in verdicts[:20])
    assert verdicts[19].trial_number == 20
    assert verdicts[20].trial_number == 21
    assert verdicts[20].eligible_for_promotion is False


def test_trial_51_raises_typed_error_and_stores_nothing(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    ledger = TrialLedger(run_id="RUNID01", path=path)
    _record_many(ledger, 50)
    assert len(ledger) == 50
    with pytest.raises(TooManyTrialsError, match="51"):
        ledger.record_trial("params-hash-051")
    assert len(ledger) == 50
    assert len(path.read_text(encoding="utf-8").splitlines()) == 50
    reopened = TrialLedger(run_id="RUNID01", path=path)
    assert len(reopened) == 50


def test_ledger_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "trials.jsonl"
    ledger = TrialLedger(run_id="RUNID01", path=path)
    first = [ledger.record_trial(f"params-hash-{i:03d}") for i in range(1, 4)]
    reopened = TrialLedger(run_id="RUNID01", path=path)
    assert reopened.trials == tuple(first)
    assert reopened.run_id == "RUNID01"


def test_ledger_path_defaults_to_var_backtest_runid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    ledger = TrialLedger(run_id="RUNID01")
    assert ledger.path == Path("var/backtest") / "RUNID01" / "trials.jsonl"
    ledger.record_trial("params-hash-001")
    assert (tmp_path / "var" / "backtest" / "RUNID01" / "trials.jsonl").is_file()


def test_empty_run_id_rejected() -> None:
    with pytest.raises(ValueError, match="run_id"):
        TrialLedger(run_id="")


def test_empty_params_hash_rejected(tmp_path: Path) -> None:
    ledger = TrialLedger(run_id="RUNID01", path=tmp_path / "trials.jsonl")
    with pytest.raises(ValueError, match="params_hash"):
        ledger.record_trial("")
