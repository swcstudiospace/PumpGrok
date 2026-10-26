"""Review round 1 settings identity and replay threading (findings 9 and 20).

The risk budget and engine limits a search evaluates reach every replay, and the
settings identity covers the filter, exits, risk budget and limits together.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import pumpgrok.backtest.evaluate as evaluate_module
from pumpgrok.backtest.evaluate import CandidateParams, evaluated_settings_hash
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.report import BacktestReport, render
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.risk.limits import EngineLimits


def test_identity_for_desk_defaults_matches_explicit_defaults() -> None:
    params = CandidateParams()
    explicit = evaluated_settings_hash(params, risk_budget=RiskBudget(), limits=EngineLimits())
    assert evaluated_settings_hash(params) == explicit


def test_identity_changes_when_one_risk_limit_changes() -> None:
    """F9: a different risk limit is a different evaluated configuration."""
    params = CandidateParams()
    tighter = RiskBudget(max_trade_fraction=Decimal("0.01"))
    tighter_hash = evaluated_settings_hash(params, risk_budget=tighter)
    assert tighter_hash != evaluated_settings_hash(params)


def test_identity_changes_for_limits_exits_and_filter() -> None:
    """F9: every evaluated section moves the identity, not only the filter."""
    base = evaluated_settings_hash(CandidateParams())
    limited = evaluated_settings_hash(CandidateParams(), limits=EngineLimits(max_slippage_bps=250))
    assert limited != base
    assert evaluated_settings_hash(CandidateParams(exits={"stop_loss_pct": 25})) != base
    assert evaluated_settings_hash(CandidateParams(filter={"min_unique_buyers": 7})) != base


def test_search_hands_the_configured_budget_and_limits_to_every_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F9: the budget and limits the search receives are the ones each replay evaluates."""
    budget = RiskBudget(max_trade_fraction=Decimal("0.01"))
    limits = EngineLimits(max_slippage_bps=250)
    seen: list[tuple[Any, Any]] = []
    real_replay = evaluate_module.run_once_replay

    def recording(dataset_dir: Any, filter_cfg: Any, **kwargs: Any) -> Any:
        seen.append((kwargs["budget"], kwargs["limits"]))
        return real_replay(dataset_dir, filter_cfg, **kwargs)

    monkeypatch.setattr(evaluate_module, "run_once_replay", recording)
    run_search(
        "smoke",
        [{}],
        1,
        11,
        run_id="BUDGET01",
        ledger_path=tmp_path / "trials.jsonl",
        risk_budget=budget,
        limits=limits,
    )

    # Three tuning folds and the holdout replay: each receives the configured objects.
    assert len(seen) == 4
    assert all(got_budget is budget for got_budget, _ in seen)
    assert all(got_limits is limits for _, got_limits in seen)


def test_search_without_budget_replays_with_the_replay_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F9: omitting the budget and limits keeps today's replay defaults."""
    seen: list[tuple[Any, Any]] = []
    real_replay = evaluate_module.run_once_replay

    def recording(dataset_dir: Any, filter_cfg: Any, **kwargs: Any) -> Any:
        seen.append((kwargs["budget"], kwargs["limits"]))
        return real_replay(dataset_dir, filter_cfg, **kwargs)

    monkeypatch.setattr(evaluate_module, "run_once_replay", recording)
    run_search("smoke", [{}], 1, 11, run_id="DEFAULT01", ledger_path=tmp_path / "trials.jsonl")

    assert len(seen) == 4
    assert all(got_budget == RiskBudget() for got_budget, _ in seen)
    assert all(got_limits == EngineLimits() for _, got_limits in seen)


def test_holdout_ledger_path_keeps_the_winner_holdout_rows(tmp_path: Path) -> None:
    """F20: the holdout ledger lands at the caller's path and its net is the reported one."""
    holdout = tmp_path / "run" / "holdout.sqlite"
    result = run_search(
        "smoke",
        [{"filter": {"min_unique_buyers": 5}}],
        1,
        11,
        run_id="HOLD01",
        ledger_path=tmp_path / "trials.jsonl",
        holdout_ledger_path=holdout,
    )

    assert holdout.is_file()
    assert result.holdout_net_lamports == evaluate_module._net_lamports(holdout)


def test_report_notes_describe_the_identity_and_refused_fees() -> None:
    """Report text: the identity note names the full configuration; fees include refusals."""
    report = BacktestReport(
        run_id="R1",
        dataset="smoke",
        dataset_digest="0" * 64,
        seed=11,
        filter_settings_hash="1" * 64,
        param_set_hash="2" * 64,
        code_version="test",
        holdout_id="smoke-holdout",
        holdout_events=1,
        tuning_events=1,
        trial_count=1,
        max_eligible_trials=50,
        max_allowed_trials=50,
        eligible_for_promotion=True,
        promotion_eligible=False,
        venue_fee_bps=0,
        base_fee_lamports=0,
        network_cost_lamports=0,
        realized_slippage_bps_total=0,
        realized_fees_lamports_total=0,
    )

    text = render(report)

    assert "full evaluated configuration: filter, exits, risk budget and limits" in text
    assert "plus fees paid by refused attempts" in text
    assert "each fee counts once" in text
