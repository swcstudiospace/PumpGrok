"""UPG-02: the promotion gate blocks each cause with its typed reason.

One case per blocking reason (out-of-bounds, failed holdout, divergence
breach, search above 20 trials, below autonomous-paper level), plus the
passing candidate and the gate-order rule that the first failure wins.
Offline only: temp ledger, in-package bounds, no network.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.bounds import Bounds, load_bounds
from pumpgrok.upgrade.gate import (
    REASON_BELOW_AUTONOMY_LEVEL,
    REASON_DIVERGENCE_BREACH,
    REASON_HOLDOUT_FAILED,
    REASON_OUT_OF_BOUNDS,
    REASON_PASS,
    REASON_TOO_MANY_TRIALS,
    evaluate_candidate,
)
from pumpgrok.upgrade.params import ParamSet

BOUNDS: Bounds = load_bounds()

IN_BOUNDS = ParamSet(filter={"min_unique_buyers": 5})
OUT_OF_BOUNDS = ParamSet(filter={"min_unique_buyers": 5000})


def _report(total_return: str = "0.01", sharpe: str = "0.10") -> MetricsReport:
    """One same-window summary with the given return and Sharpe-style ratio."""
    return MetricsReport(
        total_return=Decimal(total_return),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal(sharpe),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _search(params: ParamSet, **overrides) -> HarnessResult:
    """An eligible passing search result for params, with caller overrides."""
    fields: dict = {
        "best_params_hash": params.content_hash,
        "holdout_id": "smoke-holdout",
        "trial_count": 3,
        "eligible_for_promotion": True,
        "holdout_net_lamports": 100,
        "best_net_lamports": 50,
    }
    fields.update(overrides)
    return HarnessResult(**fields)


def _store(tmp_path, *, autonomous: bool) -> LedgerStore:
    """A temp ledger reading as autonomous-paper, or manual-ticket default."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    if autonomous:
        store.append_batch(
            autonomy_rows(
                "autonomous-paper",
                "human:UPGRADE-TEST",
                previous="",
                ts_utc="2026-01-01T00:00:00Z",
                source="paper",
                correlation_id="upgrade-gate-test",
            )
        )
        assert read_autonomy(store) == "autonomous-paper"
    return store


def _evaluate(tmp_path, params, **overrides):
    """Evaluate params with every other dimension passing unless overridden."""
    store = overrides.pop("store", None)
    close = False
    if store is None:
        store = _store(tmp_path, autonomous=True)
        close = True
    try:
        return evaluate_candidate(
            params,
            bounds=overrides.pop("bounds", BOUNDS),
            search=overrides.pop("search", _search(params)),
            run_id=overrides.pop("run_id", "RUNID-TEST-01"),
            store=store,
            backtest=overrides.pop("backtest", _report()),
            paper=overrides.pop("paper", _report()),
        )
    finally:
        if close:
            store.close()


def test_passing_candidate_is_eligible(tmp_path) -> None:
    """In-bounds set, few trials, autonomous-paper, positive holdout, no gap."""
    verdict = _evaluate(tmp_path, IN_BOUNDS)
    assert verdict.promotion_eligible is True
    assert verdict.reason == REASON_PASS
    assert IN_BOUNDS.content_hash in verdict.detail


def test_out_of_bounds_blocks(tmp_path) -> None:
    """A value outside the version-controlled bounds blocks with its reason."""
    verdict = _evaluate(tmp_path, OUT_OF_BOUNDS)
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_OUT_OF_BOUNDS


def test_search_above_20_trials_blocks(tmp_path) -> None:
    """A 21-trial search is ineligible even when every other check passes."""
    verdict = _evaluate(
        tmp_path,
        IN_BOUNDS,
        search=_search(IN_BOUNDS, trial_count=21, eligible_for_promotion=False),
    )
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_TOO_MANY_TRIALS


def test_below_autonomous_paper_blocks(tmp_path) -> None:
    """The manual-ticket default level blocks promotion."""
    store = _store(tmp_path, autonomous=False)
    try:
        verdict = _evaluate(tmp_path, IN_BOUNDS, store=store)
    finally:
        store.close()
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_BELOW_AUTONOMY_LEVEL


def test_failed_holdout_blocks(tmp_path) -> None:
    """Zero measured net on the unseen window blocks promotion."""
    verdict = _evaluate(tmp_path, IN_BOUNDS, search=_search(IN_BOUNDS, holdout_net_lamports=0))
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_HOLDOUT_FAILED


def test_negative_holdout_blocks(tmp_path) -> None:
    """A losing holdout blocks promotion the same way an empty one does."""
    verdict = _evaluate(tmp_path, IN_BOUNDS, search=_search(IN_BOUNDS, holdout_net_lamports=-40))
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_HOLDOUT_FAILED


def test_divergence_breach_blocks(tmp_path) -> None:
    """A 9-point return gap trips the D7 defaults and blocks promotion."""
    verdict = _evaluate(tmp_path, IN_BOUNDS, backtest=_report(total_return="0.10"))
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_DIVERGENCE_BREACH


def test_first_failure_wins_in_gate_order(tmp_path) -> None:
    """Out-of-bounds beats trials: G-08 names one deterministic cause."""
    verdict = _evaluate(
        tmp_path,
        OUT_OF_BOUNDS,
        search=_search(OUT_OF_BOUNDS, trial_count=21, eligible_for_promotion=False),
    )
    assert verdict.promotion_eligible is False
    assert verdict.reason == REASON_OUT_OF_BOUNDS


def test_candidate_must_match_search_winner(tmp_path) -> None:
    """A candidate cannot promote on another set's holdout result."""
    with pytest.raises(ValueError, match="does not match the search winner"):
        _evaluate(
            tmp_path,
            IN_BOUNDS,
            search=_search(OUT_OF_BOUNDS),
        )


def test_empty_run_id_is_refused(tmp_path) -> None:
    """An empty backtest run id fails closed instead of recording blindly."""
    with pytest.raises(ValueError, match="run_id"):
        _evaluate(tmp_path, IN_BOUNDS, run_id="")
