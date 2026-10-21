"""Characterization: scoring matrix (STRUCT-003).

Pins ``engine/scoring.py`` against
``vendor/grokbot-pumpfun/tests/test_scoring.py`` (vendor oracle, kept
byte-identical per R53). Logic is 1:1; the config travels as settings
sections (``ScoringWeights`` plus ``FilterSettings``) instead of the vendor
``Config``.
"""

from __future__ import annotations

import pytest

from pumpgrok.config.settings import FilterSettings, ScoringWeights
from pumpgrok.engine.models import (
    Analysis,
    AuditResult,
    NarrativeResult,
    Scores,
    TimingResult,
    Token,
    TokenMetrics,
)
from pumpgrok.engine.scoring import (
    compute_scores,
    normalized_weights,
    passes_threshold,
    weakest_component,
)


@pytest.fixture
def weights() -> ScoringWeights:
    return ScoringWeights(audit=0.30, narrative=0.25, timing=0.15, metrics=0.30)


@pytest.fixture
def filter_cfg() -> FilterSettings:
    return FilterSettings(min_total_score=0.65)


def perfect_analysis() -> Analysis:
    return Analysis(
        token=Token(mint="M"),
        metrics=TokenMetrics(risk_score=0.0),
        audit=AuditResult(
            coordinated_buying=False,
            wash_trading=False,
            creator_dump_prep=False,
            bundled_launch=False,
            organic_buyer_share=1.0,
            confidence=1.0,
        ),
        narrative=NarrativeResult(
            trend_fit=1.0, virality=1.0, community_signals=1.0, launch_timing=1.0
        ),
        timing=TimingResult(market_sentiment=1.0, meme_season=1.0, volume_level=1.0),
    )


def worst_analysis() -> Analysis:
    return Analysis(
        token=Token(mint="M"),
        metrics=TokenMetrics(risk_score=10.0),
        audit=AuditResult.pessimistic("test"),
        narrative=NarrativeResult.pessimistic("test"),
        timing=TimingResult.pessimistic("test"),
    )


# --- bounds ------------------------------------------------------------------


def test_perfect_analysis_scores_one(weights: ScoringWeights) -> None:
    scores = compute_scores(perfect_analysis(), weights)
    assert scores.total == pytest.approx(1.0)
    assert (scores.audit, scores.narrative, scores.timing, scores.metrics) == (1.0, 1.0, 1.0, 1.0)


def test_worst_analysis_scores_zero(weights: ScoringWeights) -> None:
    scores = compute_scores(worst_analysis(), weights)
    assert scores.total == pytest.approx(0.0)


def test_score_never_leaves_unit_interval(weights: ScoringWeights) -> None:
    """Even if a model returns garbage outside 0..1, the total stays in 0..1."""
    analysis = perfect_analysis()
    analysis.narrative = NarrativeResult(
        trend_fit=5.0, virality=5.0, community_signals=5.0, launch_timing=5.0
    )
    scores = compute_scores(analysis, weights)
    assert 0.0 <= scores.total <= 1.0
    assert scores.narrative == 1.0


def test_missing_components_count_as_zero(weights: ScoringWeights) -> None:
    """An agent that did not run is a zero, not a skipped component: an
    agent failure must not raise the final score."""
    analysis = perfect_analysis()
    analysis.audit = None
    scores = compute_scores(analysis, weights)
    assert scores.audit == 0.0
    assert scores.total == pytest.approx(0.70)


# --- weights -----------------------------------------------------------------


def test_weights_are_normalized() -> None:
    weights = normalized_weights(ScoringWeights(audit=2.0, narrative=2.0, timing=2.0, metrics=2.0))
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["audit"] == pytest.approx(0.25)


def test_degenerate_weights_fall_back_to_equal() -> None:
    weights = normalized_weights(ScoringWeights(audit=0.0, narrative=0.0, timing=0.0, metrics=0.0))
    assert weights == {"audit": 0.25, "narrative": 0.25, "timing": 0.25, "metrics": 0.25}


def test_negative_weight_treated_as_zero() -> None:
    weights = normalized_weights(ScoringWeights(audit=-1.0, narrative=1.0, timing=1.0, metrics=1.0))
    assert weights["audit"] == 0.0
    assert sum(weights.values()) == pytest.approx(1.0)


def test_unnormalized_weights_preserve_proportions(weights: ScoringWeights) -> None:
    skewed = ScoringWeights(audit=3.0, narrative=2.5, timing=1.5, metrics=3.0)
    scores = compute_scores(perfect_analysis(), skewed)
    assert scores.total == pytest.approx(1.0)


# --- component arithmetic ----------------------------------------------------


def test_audit_flags_penalize_score(weights: ScoringWeights) -> None:
    analysis = perfect_analysis()
    analysis.audit = AuditResult(
        coordinated_buying=True,  # -0.25
        wash_trading=False,
        creator_dump_prep=False,
        bundled_launch=False,
        organic_buyer_share=0.8,
        confidence=0.9,
    )
    scores = compute_scores(analysis, weights)
    assert scores.audit == pytest.approx(0.55)
    assert scores.total == pytest.approx(1.0 - 0.30 * 0.45)


def test_timing_anomalies_penalize_score(weights: ScoringWeights) -> None:
    analysis = perfect_analysis()
    analysis.timing = TimingResult(
        market_sentiment=1.0,
        meme_season=1.0,
        volume_level=1.0,
        anomalies=["solana_outage", "btc_dump"],
    )
    scores = compute_scores(analysis, weights)
    assert scores.timing == pytest.approx(0.8)


def test_metrics_component_mirrors_risk_score(weights: ScoringWeights) -> None:
    analysis = perfect_analysis()
    analysis.metrics = TokenMetrics(risk_score=7.0)
    scores = compute_scores(analysis, weights)
    assert scores.metrics == pytest.approx(0.3)


# --- threshold ---------------------------------------------------------------


def test_threshold_boundary_is_inclusive(filter_cfg: FilterSettings) -> None:
    ok, _ = passes_threshold(Scores(total=0.65), filter_cfg)
    assert ok
    ok, reason = passes_threshold(Scores(total=0.6499), filter_cfg)
    assert not ok and reason.startswith("score_below_threshold")


def test_weakest_component_named() -> None:
    name, value = weakest_component(Scores(audit=0.9, narrative=0.2, timing=0.8, metrics=0.7))
    assert (name, value) == ("narrative", 0.2)
