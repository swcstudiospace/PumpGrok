"""Meme-potential agent: not the chain, the meme itself.

Port of ``vendor/grokbot-pumpfun/src/agents/narrative.py`` with the prompt
translated to English. The question is whether the launch can spread or is
another clone of yesterday: four independent 0..1 scores. Missing data is a
low score, never an average one; clones of popular tickers score harshly.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pumpgrok.engine.agents.base import JSON_ONLY, GrokAgent
from pumpgrok.engine.models import NarrativeResult, Token

NARRATIVE_PROMPT = f"""You are a crypto-twitter meme culture analyst. Score
the meme potential of a freshly launched pump.fun token.

Give four independent scores from 0.0 to 1.0:
- trend_fit: fit with the current trend. 1.0 means the topic is hot right
  now, 0.0 means a dead or exhausted topic, a copy of yesterday's hype.
- virality: virality of the meme itself. Does the name stick, does the
  preview image work, is there a joke worth forwarding.
- community_signals: signs of a living community. Real twitter and telegram
  links, a meaningful description, traces of a community that existed before
  the launch. Empty or planted links mean a low score.
- launch_timing: timeliness. First on a new topic scores high, the hundredth
  clone scores low, an early bet on an unripe topic scores middling.

Missing data is a low score, not an average one. Judge clones of popular
tickers strictly.

Answer format:
{{
  "trend_fit": 0.0-1.0,
  "virality": 0.0-1.0,
  "community_signals": 0.0-1.0,
  "launch_timing": 0.0-1.0,
  "reasoning": "2-3 sentences grounding the scores"
}}

{JSON_ONLY}"""


class NarrativeAgent(GrokAgent):
    """Meme-potential analyst on the fast model."""

    name: ClassVar[str] = "narrative"
    prompt: ClassVar[str] = NARRATIVE_PROMPT
    result_model: ClassVar[type] = NarrativeResult

    def build_user_message(self, token: Token, market_context: str | None = None) -> str:
        payload: dict[str, Any] = {
            "name": token.name,
            "symbol": token.symbol,
            "description": token.description,
            "image_uri": token.image_uri,
            "links": {
                "twitter": token.twitter,
                "telegram": token.telegram,
                "website": token.website,
            },
            "age_seconds": round(token.age_seconds(self._clock.now())),
            "unique_buyers": token.unique_buyers,
            "market_cap_sol": round(token.market_cap_sol, 3),
        }
        if market_context:
            payload["market_context"] = market_context
        return json.dumps(payload, ensure_ascii=False)

    def fallback(self, reason: str) -> NarrativeResult:
        return NarrativeResult.pessimistic(reason)
