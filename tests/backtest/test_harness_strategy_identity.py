"""STR-06: the harness trial identity covers strategy parameter values.

Two candidate sets that differ only in a strategy parameter must record
distinct trial hashes in the TrialLedger, and the winning best_params_hash
must equal the CandidateParams identity that carries the strategy value, so
an operator can tell which strategy parameters a trial used.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.backtest.candidate import CandidateParams
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.trials import TrialLedger


def test_strategy_only_difference_records_distinct_trial_identities(
    tmp_path: Path,
) -> None:
    first = {"strategy": {"momentum_breakout": {"breakout_bps": 100}}}
    second = {"strategy": {"momentum_breakout": {"breakout_bps": 200}}}
    result = run_search(
        "smoke",
        [first, second],
        2,
        11,
        run_id="STRATID01",
        ledger_path=tmp_path / "trials.jsonl",
    )

    ledger = TrialLedger(run_id="STRATID01", path=tmp_path / "trials.jsonl")
    recorded = [verdict.params_hash for verdict in ledger.trials]
    expected = [
        CandidateParams(**first).content_hash,
        CandidateParams(**second).content_hash,
    ]
    assert recorded == expected
    assert len(set(recorded)) == 2
    assert result.best_params_hash in expected
    # A strategy-only set is not the legacy identity: hashes never collide
    # with the same set minus strategy overrides.
    assert CandidateParams().content_hash not in recorded
