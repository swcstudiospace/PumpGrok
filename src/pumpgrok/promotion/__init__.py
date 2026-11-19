"""Promotion lifecycle: stages, thresholds, reset and demotion (PRM-01 to PRM-04, PRM-06).

Stages are PromotionStageSet ledger rows. The step into PAPER needs an eligible verdict from
upgrade.gate.evaluate_candidate; the step into LIVE_ELIGIBLE also needs the paper record to meet
config/promotion_thresholds.toml. A parameter hash change resets a strategy to BACKTEST.

demote() lives in pumpgrok.promotion.demote and is imported from there. It is not re-exported
here, so the submodule name stays a module.
"""

from pumpgrok.promotion.stages import (
    Stage,
    StageRefused,
    advance_stage,
    current_stage,
    paper_record,
)
from pumpgrok.promotion.thresholds import (
    PaperRecord,
    PromotionThresholdError,
    PromotionThresholds,
    evaluate_paper_record,
    load_thresholds,
)

__all__ = [
    "PaperRecord",
    "PromotionThresholdError",
    "PromotionThresholds",
    "Stage",
    "StageRefused",
    "advance_stage",
    "current_stage",
    "evaluate_paper_record",
    "load_thresholds",
    "paper_record",
]
