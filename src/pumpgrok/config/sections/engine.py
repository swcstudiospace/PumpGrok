"""Engine settings sections: launch-monitor filter, scoring, exit rules and safety thresholds.

Split out of config/settings.py (11-04, CONTEXT D-11). Each section keeps its class name, field
set, validators and defaults, so its JSON schema and default-value digest stay as pinned in
tests/config/test_settings_surface_characterization.py.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FilterSettings(BaseModel):
    """Launch-monitor admission gates (vendor FilterConfig, ASCII codes)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_unique_buyers: int = Field(default=5, ge=0)
    max_curve_progress: float = Field(default=0.40, ge=0)
    require_metadata: bool = True
    min_age_seconds: float = Field(default=120.0, ge=0)
    max_risk_score: float = Field(default=7.0, ge=0)
    min_total_score: float = Field(default=0.65, ge=0)
    block_creator_after_rugs: int = Field(default=1, ge=0)
    rug_loss_pct: float = Field(default=60.0, ge=0)
    one_position_per_creator: bool = True
    forget_creators_after_days: float = Field(default=30.0, ge=0)


class ScoringWeights(BaseModel):
    """Component weights; must sum to 1 downstream (vendor ScoringWeights)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    audit: float = 0.30
    narrative: float = 0.25
    timing: float = 0.15
    metrics: float = 0.30


class ScoringSettings(BaseModel):
    """Engine scoring knobs (vendor ScoringConfig)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    timing_cache_seconds: float = Field(default=900.0, ge=0)


class ExitsSettings(BaseModel):
    """Exit-rule thresholds. Separate from ``risk`` (Pitfall 15, R20)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_loss_pct: float = Field(default=30.0, ge=0)
    take_profit_pct: float = Field(default=120.0, ge=0)
    trailing_stop_pct: float = Field(default=35.0, ge=0)
    max_hold_seconds: float = Field(default=3600.0, ge=0)
    stop_loss_poll_seconds: float = Field(default=15.0, ge=0)


class SafetyThresholds(BaseModel):
    """Score-report check thresholds (TOOL-003; REVIEW defaults from agents/risk.md)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transfer_tax_hard_fail_pct: float = Field(default=10.0, ge=0)
    transfer_tax_warn_pct: float = Field(default=5.0, ge=0)
    top10_concentration_warn_pct: float = Field(default=20.0, ge=0)
    top10_concentration_fail_pct: float = Field(default=25.0, ge=0)
    liquidity_multiple_min: float = Field(default=10.0, ge=0)
    liquidity_multiple_recommended: float = Field(default=20.0, ge=0)
    lp_lock_min_days: float = Field(default=180.0, ge=0)
    creator_share_veto: float = Field(default=0.25, ge=0)
    top5_share_veto: float = Field(default=0.80, ge=0)
    kill_below_score: float = Field(default=40.0, ge=0)
    conditional_below_score: float = Field(default=70.0, ge=0)


class SafetySettings(BaseModel):
    """Safety scoring knobs (TOOL-003). Secrets never live here (STRUCT-008)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thresholds: SafetyThresholds = Field(default_factory=SafetyThresholds)
