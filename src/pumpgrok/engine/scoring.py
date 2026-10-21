"""Scoring matrix. Code, no LLM.

Reduces four components — audit, narrative, timing, metrics — to a single
0..1 number with weights from the settings. This is the cheap gate before
the expensive checker: anything below ``filter.min_total_score`` is logged
as a skip with a per-component breakdown and never reaches grok-4.

Weights from the settings are normalized: if the user writes 0.5/0.5/0.5/
0.5, the total still lands in 0..1 and the proportions survive.

Port of the retired oracle ``src/scoring.py``. Logic is 1:1; only the
config travels differently (settings sections instead of the vendor
``Config``) and the prose is English.
"""

from __future__ import annotations

from pumpgrok.config.settings import FilterSettings, ScoringWeights
from pumpgrok.engine.models import Analysis, Scores

# Components that are missing (an agent did not run) count as zero — not
# the average and not "skip the component". Absence of signal is not an
# argument in favor.
MISSING_COMPONENT = 0.0


def normalized_weights(weights: ScoringWeights) -> dict[str, float]:
    raw = {
        "audit": max(0.0, weights.audit),
        "narrative": max(0.0, weights.narrative),
        "timing": max(0.0, weights.timing),
        "metrics": max(0.0, weights.metrics),
    }
    total = sum(raw.values())
    if total <= 0:
        # Degenerate config: equal weights beat dividing by zero.
        return dict.fromkeys(raw, 0.25)
    return {key: value / total for key, value in raw.items()}


def compute_scores(analysis: Analysis, weights: ScoringWeights) -> Scores:
    """Decomposed per-component scoring plus total."""
    normalized = normalized_weights(weights)

    components = {
        "audit": analysis.audit.score if analysis.audit else MISSING_COMPONENT,
        "narrative": analysis.narrative.score if analysis.narrative else MISSING_COMPONENT,
        "timing": analysis.timing.score if analysis.timing else MISSING_COMPONENT,
        "metrics": analysis.metrics.quality,
    }
    components = {key: _clamp(value) for key, value in components.items()}

    total = sum(components[key] * normalized[key] for key in components)

    return Scores(
        audit=round(components["audit"], 4),
        narrative=round(components["narrative"], 4),
        timing=round(components["timing"], 4),
        metrics=round(components["metrics"], 4),
        total=round(_clamp(total), 4),
    )


def passes_threshold(scores: Scores, filter_cfg: FilterSettings) -> tuple[bool, str]:
    """Whether the token makes it to the adversarial checker."""
    threshold = filter_cfg.min_total_score
    if scores.total < threshold:
        return False, f"score_below_threshold ({scores.total:.3f} < {threshold:.3f})"
    return True, "ok"


def weakest_component(scores: Scores) -> tuple[str, float]:
    """The weakest component, for the skip log."""
    named = {
        "audit": scores.audit,
        "narrative": scores.narrative,
        "timing": scores.timing,
        "metrics": scores.metrics,
    }
    name = min(named, key=lambda key: named[key])
    return name, named[name]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
