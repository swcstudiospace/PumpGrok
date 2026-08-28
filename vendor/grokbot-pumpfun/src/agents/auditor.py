"""Агент 1: аудит кошельков.

Метрики видят агрегаты — доли, счётчики, средние. Аудитор смотрит на сырой
поток сделок и ищет то, что в агрегатах теряется: одинаковые суммы,
интервалы меньше пяти секунд, кошельки, которые ходят вместе, продажи
самому себе, подготовку создателя к сбросу.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from ..models import AuditResult, Holder, Token, TokenMetrics, Trade
from .base import JSON_ONLY, GrokAgent

AUDITOR_PROMPT = f"""Ты — форензик-аналитик ончейн-активности на pump.fun.
Тебе дают сырые сделки и список холдеров нового мемкоина. Твоя работа —
найти манипуляцию, которую не видно в агрегированных метриках.

Ищи конкретно:
1. Координированные покупки: близкие по размеру суммы, интервалы между
   покупками меньше 5 секунд, повторяющийся ритм, кошельки с общим
   источником финансирования или последовательными адресами.
2. Wash-трейдинг: один и тот же кошелёк покупает и продаёт, круговые
   переводы, объём без прироста уникальных держателей.
3. Подготовку сброса создателем: создатель докупает с других адресов,
   концентрация у связанных кошельков, дробление позиции перед выходом.
4. Bundled launch: покупки в том же блоке или в первую секунду жизни
   токена с нескольких адресов сразу.
5. Долю органических покупателей — тех, кто не попал ни в одну из схем выше.

Будь скептичен. При недостатке данных ставь флаг в true и понижай
confidence, а не оправдывай токен.

Формат ответа:
{{
  "coordinated_buying": true|false,
  "wash_trading": true|false,
  "creator_dump_prep": true|false,
  "bundled_launch": true|false,
  "organic_buyer_share": 0.0-1.0,
  "confidence": 0.0-1.0,
  "flags": ["короткие метки найденного"],
  "reasoning": "2-3 предложения с конкретикой: адреса, суммы, интервалы"
}}

{JSON_ONLY}"""


class AuditorAgent(GrokAgent):
    name: ClassVar[str] = "auditor"
    prompt: ClassVar[str] = AUDITOR_PROMPT
    result_model: ClassVar[type] = AuditResult

    def build_user_message(
        self,
        token: Token,
        trades: list[Trade],
        holders: list[Holder],
        metrics: TokenMetrics | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "token": {
                "mint": token.mint,
                "symbol": token.symbol,
                "creator": token.creator,
                "age_seconds": round(token.age_seconds),
                "curve_progress": round(token.curve_progress, 4),
            },
            "trades": [
                {
                    "wallet": t.wallet,
                    "side": "buy" if t.is_buy else "sell",
                    "sol": round(t.sol_amount, 6),
                    "t": round(t.timestamp - token.created_timestamp, 2)
                    if token.created_timestamp
                    else t.timestamp,
                    "slot": t.slot,
                }
                for t in trades
            ],
            "holders": [
                {"address": h.address, "share": round(h.share, 5), "is_creator": h.is_creator}
                for h in holders
            ],
        }
        if metrics is not None:
            payload["computed_metrics"] = metrics.model_dump()
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def fallback(self, reason: str) -> AuditResult:
        return AuditResult.pessimistic(reason)
