"""Promotion lifecycle on ledger rows (PRM-01 to PRM-04, PRM-06).

Stages move BACKTEST to PAPER to LIVE_ELIGIBLE on recorded evidence
under version-controlled thresholds, with gate checks reused from the
upgrade gate through its ``paper`` parameter (no second search), no
timers and no Grok, automatic demotion, and writer discipline.
"""

from __future__ import annotations

from pumpgrok.promotion.evaluator import EvidenceView, PromotionEvaluator, evaluate_stage
from pumpgrok.promotion.stages import (
    Stage,
    StageRow,
    Transition,
    append_stage_row,
    append_transition,
    decision_log,
    read_stage_row,
)
from pumpgrok.promotion.thresholds import PromotionThresholds, load_thresholds

__all__ = [
    "EvidenceView",
    "PromotionEvaluator",
    "PromotionThresholds",
    "Stage",
    "StageRow",
    "Transition",
    "append_stage_row",
    "append_transition",
    "decision_log",
    "evaluate_stage",
    "load_thresholds",
    "read_stage_row",
]
