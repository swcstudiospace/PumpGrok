"""Агент 2: мем-потенциал.

Оценивает не ончейн, а сам мем: описание, тикер, картинку, ссылки. Вопрос
один — есть ли шанс, что это разлетится, или это очередной клон вчерашнего.
"""

from __future__ import annotations

import json
from typing import ClassVar

from ..models import NarrativeResult, Token
from .base import JSON_ONLY, GrokAgent

NARRATIVE_PROMPT = f"""Ты — аналитик мем-культуры криптотвиттера. Оцениваешь
мем-потенциал только что запущенного токена на pump.fun.

Дай четыре независимые оценки от 0.0 до 1.0:
- trend_fit: попадание в текущий тренд. 1.0 — тема прямо сейчас на слуху,
  0.0 — мёртвая или выдохшаяся тема, копия вчерашнего хайпа.
- virality: виральность самого мема. Запоминается ли название, работает ли
  картинка превью, есть ли шутка, которую хочется переслать.
- community_signals: признаки живого сообщества. Реальные ссылки на
  твиттер и телеграм, осмысленное описание, следы существовавшего до
  запуска коммьюнити. Пустые или подставные ссылки — низкая оценка.
- launch_timing: своевременность. Первый на новой теме — высоко, сотый
  клон — низко, преждевременный заход на несозревшую тему — средне.

Отсутствие данных — это низкая оценка, а не средняя. Клоны популярных
тикеров оценивай строго.

Формат ответа:
{{
  "trend_fit": 0.0-1.0,
  "virality": 0.0-1.0,
  "community_signals": 0.0-1.0,
  "launch_timing": 0.0-1.0,
  "reasoning": "2-3 предложения, чем обоснованы оценки"
}}

{JSON_ONLY}"""


class NarrativeAgent(GrokAgent):
    name: ClassVar[str] = "narrative"
    prompt: ClassVar[str] = NARRATIVE_PROMPT
    result_model: ClassVar[type] = NarrativeResult

    def build_user_message(self, token: Token, market_context: str | None = None) -> str:
        payload = {
            "name": token.name,
            "symbol": token.symbol,
            "description": token.description,
            "image_uri": token.image_uri,
            "links": {
                "twitter": token.twitter,
                "telegram": token.telegram,
                "website": token.website,
            },
            "age_seconds": round(token.age_seconds),
            "unique_buyers": token.unique_buyers,
            "market_cap_sol": round(token.market_cap_sol, 3),
        }
        if market_context:
            payload["market_context"] = market_context
        return json.dumps(payload, ensure_ascii=False)

    def fallback(self, reason: str) -> NarrativeResult:
        return NarrativeResult.pessimistic(reason)
