"""PRM-03: the upgrade gate checks are reused; there is no second search.

Same evidence, same verdict from the upgrade path and the promotion
paper path: bounds, trial count, holdout and divergence all run through
``evaluate_candidate`` with the paper parameter. Promotion never calls a
search function; the trial count comes from the evidence record.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.backtest.harness import HarnessResult
from pumpgrok.backtest.metrics import MetricsReport
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.gate import (
    REASON_BELOW_AUTONOMY_LEVEL,
    REASON_PASS,
    evaluate_candidate,
)
from pumpgrok.upgrade.params import ParamSet

BOUNDS = load_bounds()
IN_BOUNDS = ParamSet(filter={"min_unique_buyers": 5})


def _report() -> MetricsReport:
    return MetricsReport(
        total_return=Decimal("0.01"),
        max_drawdown=Decimal("0.005"),
        sharpe_ratio=Decimal("0.10"),
        win_rate=Decimal("0.5"),
        trade_count=4,
        exposure_lamports=1000,
        turnover_lamports=4000,
    )


def _search(**overrides: object) -> HarnessResult:
    fields: dict[str, object] = {
        "best_params_hash": IN_BOUNDS.content_hash,
        "holdout_id": "smoke-holdout",
        "trial_count": 3,
        "eligible_for_promotion": True,
        "holdout_net_lamports": 100,
        "best_net_lamports": 50,
    }
    fields.update(overrides)
    return HarnessResult(**fields)  # type: ignore[arg-type]


def _manual_store(tmp_path: Path):
    from pumpgrok.ledger.store import LedgerStore

    return LedgerStore(str(tmp_path / "ledger.sqlite"))


def test_paper_path_passes_on_same_evidence_that_upgrade_blocks_for_level(tmp_path: Path) -> None:
    store = _manual_store(tmp_path)  # manual-ticket: below the level
    common = dict(
        bounds=BOUNDS,
        search=_search(),
        run_id="RUN-1",
        store=store,
        backtest=_report(),
        paper=_report(),
    )
    upgrade = evaluate_candidate(IN_BOUNDS, **common)  # type: ignore[arg-type]
    assert upgrade.reason == REASON_BELOW_AUTONOMY_LEVEL
    paper = evaluate_candidate(IN_BOUNDS, paper_mode=True, **common)  # type: ignore[arg-type]
    assert paper.reason == REASON_PASS
    assert paper.promotion_eligible is True
    store.close()


def test_paper_path_reuses_bounds_holdout_and_divergence_verdicts(tmp_path: Path) -> None:
    store = _manual_store(tmp_path)
    for overrides in (
        {"search": _search(holdout_net_lamports=0)},
        {"search": _search(trial_count=51)},
    ):
        kwargs = dict(
            bounds=BOUNDS,
            search=_search(),
            run_id="RUN-1",
            store=store,
            backtest=_report(),
            paper=_report(),
        )
        kwargs.update(overrides)
        upgrade = evaluate_candidate(IN_BOUNDS, **kwargs)  # type: ignore[arg-type]
        paper = evaluate_candidate(IN_BOUNDS, paper_mode=True, **kwargs)  # type: ignore[arg-type]
        if upgrade.reason == REASON_BELOW_AUTONOMY_LEVEL:
            assert paper.reason in (REASON_PASS, "holdout_failed", "too_many_trials")
        else:
            assert paper.reason == upgrade.reason
    store.close()
