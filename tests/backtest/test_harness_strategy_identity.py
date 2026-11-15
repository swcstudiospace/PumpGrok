"""STR-06: a strategy parameter changes the harness trial identity, one hash only.

The harness records each trial under CandidateParams.content_hash. The trial
identity for a candidate carrying a strategy section must differ from the same
candidate without it, and must equal ParamSet.content_hash for that candidate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.backtest.candidate import CandidateParams
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.trials import TrialLedger
from pumpgrok.upgrade.params import ParamSet

LEGACY: dict[str, Any] = {"filter": {"min_unique_buyers": 5}}
WITH_STRATEGY: dict[str, Any] = {
    "filter": {"min_unique_buyers": 5},
    "strategy": {"momentum_breakout": {"lookback_seconds": 300}},
}


def test_strategy_param_changes_trial_identity(tmp_path: Path) -> None:
    """A recorded trial with a strategy value differs from the same trial without it."""
    ledger_path = tmp_path / "trials.jsonl"
    run_search(
        "smoke",
        [LEGACY, WITH_STRATEGY],
        2,
        11,
        run_id="STRAT01",
        ledger_path=ledger_path,
    )
    recorded = [
        verdict.params_hash for verdict in TrialLedger(run_id="STRAT01", path=ledger_path).trials
    ]
    assert len(recorded) == 2
    legacy_identity, strategy_identity = recorded
    assert strategy_identity != legacy_identity


def test_trial_identity_is_the_single_candidate_hash() -> None:
    """The trial identity equals CandidateParams.content_hash and ParamSet.content_hash."""
    candidate_hash = CandidateParams(**WITH_STRATEGY).content_hash
    assert ParamSet(**WITH_STRATEGY).content_hash == candidate_hash
    assert CandidateParams(**LEGACY).content_hash != candidate_hash
