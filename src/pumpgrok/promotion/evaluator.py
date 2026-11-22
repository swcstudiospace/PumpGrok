"""Promotion evaluator: a pure function over recorded evidence (PRM-01, T-17-07).

Forward moves require the version-controlled thresholds to be met and
the evidence (served by the Phase 16 BacktestEvidenceProvider) to grade
eligible; ineligible evidence never moves a stage. The evaluator holds
no clock, no thread, and no Grok import; evidence reads come from the
provider only, never from a fresh backtest run.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pumpgrok.promotion.stages import Stage
from pumpgrok.promotion.thresholds import PromotionThresholds

__all__ = ["EvidenceView", "PromotionEvaluator", "evaluate_stage"]

_FORWARD: dict[Stage, Stage] = {
    Stage.BACKTEST: Stage.PAPER,
    Stage.PAPER: Stage.LIVE_ELIGIBLE,
}


@dataclass(frozen=True)
class EvidenceView:
    """One recorded evidence item as the evaluator consumes it."""

    strategy_id: str
    eligible: bool
    paper_days: int = 0
    closed_trades: int = 0
    profit_factor: Decimal = Decimal("0")
    drawdown_fraction: Decimal = Decimal("1")
    param_hash: str = ""
    version_id: str = ""
    evidence_run_id: str = ""
    event_id: str = ""
    metrics: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.metrics is None:
            object.__setattr__(self, "metrics", {})


def evaluate_stage(
    current: Stage | None,
    evidence: EvidenceView,
    thresholds: PromotionThresholds,
) -> Stage:
    """Next stage for one evidence item; ineligible evidence never moves.

    A strategy with no recorded evidence stays in BACKTEST. Forward moves
    step exactly one stage per evidence item.
    """
    stage = current if current is not None else Stage.BACKTEST
    if stage not in _FORWARD:
        return stage
    if not evidence.eligible:
        return stage
    if not thresholds.meets(
        paper_days=evidence.paper_days,
        closed_trades=evidence.closed_trades,
        profit_factor=evidence.profit_factor,
        drawdown_fraction=evidence.drawdown_fraction,
    ):
        return stage
    return _FORWARD[stage]


@dataclass(frozen=True)
class PromotionEvaluator:
    """Threshold-bound stage evaluator; pure over evidence views."""

    thresholds: PromotionThresholds

    def next_stage(self, current: Stage | None, evidence: EvidenceView) -> Stage:
        """The stage after this evidence item (same as evaluate_stage)."""
        return evaluate_stage(current, evidence, self.thresholds)
