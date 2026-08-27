"""Скоринг-матрица. Код, без LLM.

Сводит четыре компонента — аудит, нарратив, тайминг, метрики — в одно
число 0..1 с весами из конфига. Это дешёвый гейт перед дорогим чекером:
всё, что не дотянуло до `filter.min_total_score`, логируется как skip с
разбивкой по компонентам и до grok-4 не доходит.

Веса из конфига нормализуются: если пользователь напишет 0.5/0.5/0.5/0.5,
итог всё равно останется в диапазоне 0..1, а пропорции сохранятся.
"""

from __future__ import annotations

from .models import Analysis, Config, Scores, ScoringWeights

# Компоненты, которых нет (агент не отработал), считаются нулём — не
# средним и не «пропустить компонент». Отсутствие сигнала не аргумент за.
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
        # Вырожденный конфиг: равные веса лучше деления на ноль.
        return dict.fromkeys(raw, 0.25)
    return {key: value / total for key, value in raw.items()}


def compute_scores(analysis: Analysis, config: Config) -> Scores:
    """Разложенный скоринг по компонентам плюс итог."""
    weights = normalized_weights(config.scoring.weights)

    components = {
        "audit": analysis.audit.score if analysis.audit else MISSING_COMPONENT,
        "narrative": analysis.narrative.score if analysis.narrative else MISSING_COMPONENT,
        "timing": analysis.timing.score if analysis.timing else MISSING_COMPONENT,
        "metrics": analysis.metrics.quality,
    }
    components = {key: _clamp(value) for key, value in components.items()}

    total = sum(components[key] * weights[key] for key in components)

    return Scores(
        audit=round(components["audit"], 4),
        narrative=round(components["narrative"], 4),
        timing=round(components["timing"], 4),
        metrics=round(components["metrics"], 4),
        total=round(_clamp(total), 4),
    )


def passes_threshold(scores: Scores, config: Config) -> tuple[bool, str]:
    """Дотянул ли токен до похода к адверсариальному чекеру."""
    threshold = config.filter.min_total_score
    if scores.total < threshold:
        return False, f"score_below_threshold ({scores.total:.3f} < {threshold:.3f})"
    return True, "ok"


def weakest_component(scores: Scores) -> tuple[str, float]:
    """Самый слабый компонент — уходит в лог как деталь причины пропуска."""
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
