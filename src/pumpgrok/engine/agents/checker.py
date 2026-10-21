"""Adversarial-check agent: the last gate before money, on the strong model.

Port of ``vendor/grokbot-pumpfun/src/agents/checker.py`` with the prompt
translated to English. It is forbidden from finding reasons to buy: it gets
every earlier verdict and looks for contradictions, missed red flags, and a
weak evidence base. ``approve: false`` is the normal, expected outcome, and
a call failure also becomes ``approve: false``.
"""

from __future__ import annotations

import json
from typing import ClassVar

from pumpgrok.engine.agents.base import JSON_ONLY, GrokAgent
from pumpgrok.engine.models import Analysis, CheckerResult

CHECKER_PROMPT = f"""You are the risk officer who signs off on or blocks a
memecoin buy. Your job is NOT to find reasons to buy. Your job is to find
reasons NOT to buy.

You get the full workup: metrics, the wallet auditor verdict, the
meme-potential score, the market state, and the final scoring.

Look for:
1. Contradictions between signals. High meme potential with low organic
   buyers. A good curve with top-5 concentration. A strong score carried by
   one component while the rest fail.
2. Red flags the earlier agents missed or underweighted.
3. A weak evidence base: low auditor confidence, few trades, missing data
   behind confident verdicts.
4. A market backdrop where even a good token will not move.

Decision rules:
- In doubt, approve: false.
- Any auditor flag firing with organic buyer share below 0.5 means
  approve: false.
- Never approve on the strength of a single strong component.

Answer format:
{{
  "approve": true|false,
  "reason": "one or two sentences, the main reason for the decision",
  "flags": ["short labels for the problems found"],
  "confidence": 0.0-1.0
}}

{JSON_ONLY}"""


class CheckerAgent(GrokAgent):
    """Risk officer on the strong model."""

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
                "age_seconds": round(token.age_seconds(self._clock.now())),
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
