"""Агент 4: адверсариальная проверка.

Последний рубеж перед деньгами и единственный, кто работает на сильной
модели. Ему запрещено искать причины купить: он получает выводы всех
предыдущих агентов и ищет, где они противоречат друг другу и что они
пропустили.

approve: false — это нормальный, ожидаемый исход. Ошибка вызова тоже
превращается в approve: false.
"""

from __future__ import annotations

import json
from typing import ClassVar

from ..models import Analysis, CheckerResult
from .base import JSON_ONLY, GrokAgent

CHECKER_PROMPT = f"""Ты — риск-офицер, который подписывает или блокирует
покупку мемкоина. Твоя работа — НЕ найти причины купить. Твоя работа —
найти причины НЕ покупать.

Тебе дают полный разбор: метрики, вывод аудитора кошельков, оценку
мем-потенциала, состояние рынка и итоговый скоринг.

Ищи:
1. Противоречия между сигналами. Высокий мем-потенциал при низкой органике
   покупателей. Хорошая кривая при концентрации у топ-5. Сильный скоринг,
   собранный одним компонентом при провале остальных.
2. Красные флаги, которые предыдущие агенты не отметили или недооценили.
3. Слабую доказательную базу: низкий confidence аудитора, мало сделок,
   отсутствие данных при уверенных выводах.
4. Рыночный фон, при котором даже хороший токен не поедет.

Правила решения:
- Сомневаешься — approve: false.
- Любой сработавший флаг аудитора при organic_buyer_share ниже 0.5 —
  approve: false.
- Не одобряй на основании одного сильного компонента.

Формат ответа:
{{
  "approve": true|false,
  "reason": "одно-два предложения, главная причина решения",
  "flags": ["короткие метки найденных проблем"],
  "confidence": 0.0-1.0
}}

{JSON_ONLY}"""


class CheckerAgent(GrokAgent):
    name: ClassVar[str] = "checker"
    prompt: ClassVar[str] = CHECKER_PROMPT
    result_model: ClassVar[type] = CheckerResult
    use_checker_model: ClassVar[bool] = True

    def build_user_message(self, analysis: Analysis) -> str:
        token = analysis.token
        payload = {
            "token": {
                "mint": token.mint,
                "name": token.name,
                "symbol": token.symbol,
                "description": token.description,
                "links": {
                    "twitter": token.twitter,
                    "telegram": token.telegram,
                    "website": token.website,
                },
                "age_seconds": round(token.age_seconds),
                "unique_buyers": token.unique_buyers,
                "curve_progress": round(token.curve_progress, 4),
            },
            "metrics": analysis.metrics.model_dump(),
            "auditor": analysis.audit.model_dump() if analysis.audit else None,
            "narrative": analysis.narrative.model_dump() if analysis.narrative else None,
            "timing": analysis.timing.model_dump() if analysis.timing else None,
            "scores": analysis.scores.model_dump(),
        }
        return json.dumps(payload, ensure_ascii=False)

    def fallback(self, reason: str) -> CheckerResult:
        return CheckerResult.pessimistic(reason)
