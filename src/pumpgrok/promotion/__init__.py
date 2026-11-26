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
    StageRefused,
    StageRow,
    Transition,
    advance_stage,
    append_stage_row,
    append_transition,
    current_stage,
    decision_log,
    paper_record,
    read_stage_row,
)
from pumpgrok.promotion.thresholds import (
    PaperRecord,
    PromotionThresholdError,
    PromotionThresholds,
    evaluate_paper_record,
    load_thresholds,
)

__all__ = [
    "EvidenceView",
    "PaperRecord",
    "PromotionEvaluator",
    "PromotionThresholdError",
    "PromotionThresholds",
    "Stage",
    "StageRefused",
    "StageRow",
    "Transition",
    "advance_stage",
    "append_stage_row",
    "append_transition",
    "current_stage",
    "decision_log",
    "evaluate_paper_record",
    "evaluate_stage",
    "load_thresholds",
    "paper_record",
    "read_stage_row",
]
