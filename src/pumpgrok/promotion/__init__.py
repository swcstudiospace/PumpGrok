"""Promotion lifecycle: stages, thresholds, reset and demotion (PRM-01 to PRM-04, PRM-06).

Stages are PromotionStageSet ledger rows. The step into PAPER needs an eligible verdict from
upgrade.gate.evaluate_candidate; the step into LIVE_ELIGIBLE also needs the paper record to meet
config/promotion_thresholds.toml. A parameter hash change resets a strategy to BACKTEST.

demote() lives in pumpgrok.promotion.demote and is imported from there. It is not re-exported
here, so the submodule name stays a module.
"""

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
    "default_thresholds_path",
    "evaluate_paper_record",
    "evaluate_stage",
    "load_thresholds",
    "paper_record",
    "read_stage_row",
]