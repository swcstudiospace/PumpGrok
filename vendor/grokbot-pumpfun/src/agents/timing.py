"""Агент 3: момент рынка.

Оценивает не токен, а фон: настроение, идёт ли мем-сезон, какие сейчас
объёмы на pump.fun, нет ли аномалий. Ответ одинаков для всех токенов в
пределах окна, поэтому результат кэшируется на `timing_cache_seconds`
(по умолчанию 15 минут) — иначе каждый лонч оплачивал бы один и тот же вывод.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, ClassVar

from ..models import Config, TimingResult
from .base import JSON_ONLY, GrokAgent

TIMING_PROMPT = f"""Ты — аналитик рыночного режима для мемкоинов Solana.
Оцениваешь не конкретный токен, а фон, на котором он запускается.

Дай три оценки от 0.0 до 1.0 и список аномалий:
- market_sentiment: общее настроение по Solana и мемкоинам. 1.0 — жадность
  и приток, 0.0 — паника, каскад ликвидаций, отток.
- meme_season: идёт ли сейчас мем-сезон. Высоко, если свежие лончи реально
  доходят до Raydium и держатся; низко, если всё сдувается за час.
- volume_level: уровень объёмов и активности на pump.fun относительно
  обычного для этого времени суток.
- anomalies: короткие метки того, что ломает нормальную торговлю —
  "solana_outage", "btc_dump", "weekend_thin_liquidity", "macro_event",
  "post_rug_panic". Пустой список, если фон обычный.

Если данных о рынке мало — занижай оценки и говори об этом в reasoning.

Формат ответа:
{{
  "market_sentiment": 0.0-1.0,
  "meme_season": 0.0-1.0,
  "volume_level": 0.0-1.0,
  "anomalies": ["метки"],
  "reasoning": "2-3 предложения"
}}

{JSON_ONLY}"""


class TimingAgent(GrokAgent):
    name: ClassVar[str] = "timing"
    prompt: ClassVar[str] = TIMING_PROMPT
    result_model: ClassVar[type] = TimingResult

    def __init__(
        self,
        config: Config,
        client: Any | None = None,
        ops: Any | None = None,
    ) -> None:
        super().__init__(config, client, ops)
        self.cache_seconds = config.scoring.timing_cache_seconds
        self._cached: TimingResult | None = None
        self._lock = asyncio.Lock()

    def build_user_message(self, market_snapshot: dict[str, Any] | None = None) -> str:
        payload = {
            "asked_at_unix": int(time.time()),
            "market": market_snapshot or {},
        }
        return json.dumps(payload, ensure_ascii=False)

    def fallback(self, reason: str) -> TimingResult:
        return TimingResult.pessimistic(reason)

    # -- кэш ---------------------------------------------------------------

    def cache_is_fresh(self, now: float | None = None) -> bool:
        if self._cached is None:
            return False
        now = now or time.time()
        return (now - self._cached.fetched_at) < self.cache_seconds

    async def get(self, market_snapshot: dict[str, Any] | None = None) -> TimingResult:
        """Свежая оценка рынка: из кэша или новым вызовом.

        Лок нужен, чтобы пачка токенов, подошедших одновременно, не устроила
        три параллельных одинаковых запроса.
        """
        if self.cache_is_fresh():
            return self._cached  # type: ignore[return-value]
        async with self._lock:
            if self.cache_is_fresh():
                return self._cached  # type: ignore[return-value]
            result: TimingResult = await self.run(market_snapshot)
            result.fetched_at = time.time()
            # Пессимистичный фолбэк не кэшируем: сбой не должен блокировать
            # рынок на все 15 минут.
            if "agent_failure" not in result.anomalies:
                self._cached = result
            return result

    def invalidate(self) -> None:
        self._cached = None
