"""Market-moment agent: not the token, the backdrop it launches into.

Port of the retired oracle ``src/agents/timing.py`` with the prompt
translated to English. The verdict is identical for every token inside one
window, so it is cached for ``cache_seconds`` (15 minutes by default):
without the cache every launch would pay for the same verdict. The cache
runs on explicit ``now`` values threaded by the caller, never on wall time.
A pessimistic fallback is never cached: a failure must not block the market
for the whole window.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from pumpgrok.config.settings import GrokSettings
from pumpgrok.engine.agents.base import JSON_ONLY, GrokAgent
from pumpgrok.engine.models import TimingResult
from pumpgrok.grok.gateway import Candidate, GrokGateway
from pumpgrok.replay.clock import Clock

TIMING_PROMPT = f"""You are a market-regime analyst for Solana memecoins.
Score not a specific token but the backdrop it launches into.

Give three scores from 0.0 to 1.0 plus a list of anomalies:
- market_sentiment: overall mood on Solana and memecoins. 1.0 is greed and
  inflow, 0.0 is panic, liquidation cascades, outflow.
- meme_season: whether meme season is on. High when fresh launches really
  reach Raydium and hold; low when everything deflates within an hour.
- volume_level: volume and activity level on pump.fun relative to the usual
  for this time of day.
- anomalies: short labels for whatever breaks normal trading:
  "solana_outage", "btc_dump", "weekend_thin_liquidity", "macro_event",
  "post_rug_panic". An empty list when the backdrop is ordinary.

When market data is thin, lower the scores and say so in the reasoning.

Answer format:
{{
  "market_sentiment": 0.0-1.0,
  "meme_season": 0.0-1.0,
  "volume_level": 0.0-1.0,
  "anomalies": ["labels"],
  "reasoning": "2-3 sentences"
}}

{JSON_ONLY}"""


class TimingAgent(GrokAgent):
    """Market-regime analyst on the fast model, with an explicit-time cache."""

    name: ClassVar[str] = "timing"
    prompt: ClassVar[str] = TIMING_PROMPT
    result_model: ClassVar[type] = TimingResult

    def __init__(
        self,
        grok: GrokSettings,
        *,
        gateway: GrokGateway,
        clock: Clock,
        cache_seconds: float,
    ) -> None:
        super().__init__(grok, gateway=gateway, clock=clock)
        self.cache_seconds = cache_seconds
        self._cached: TimingResult | None = None

    def build_user_message(self, market_snapshot: dict[str, Any] | None = None) -> str:
        payload = {
            "asked_at_unix": int(self._clock.now()),
            "market": market_snapshot or {},
        }
        return json.dumps(payload, ensure_ascii=False)

    def fallback(self, reason: str) -> TimingResult:
        return TimingResult.pessimistic(reason)

    def cache_is_fresh(self, now: float) -> bool:
        """Whether the cached verdict still covers ``now``."""
        if self._cached is None:
            return False
        age = now - self._cached.fetched_at
        # A clock stepped back before the fetch has a negative age: not fresh.
        return 0.0 <= age < self.cache_seconds

    async def get(
        self,
        market_snapshot: dict[str, Any] | None = None,
        *,
        now: float,
        event_id: str,
        candidate: Candidate,
    ) -> TimingResult:
        """A fresh market verdict: from cache or from a new call.

        Concurrent callers share one model call only when the gateway coalesces
        their admitted requests (identical text, in flight together). Otherwise
        each caller that finds the cache stale makes its own call. No lock is
        taken: a lock would serialize every launch on the clock.
        """
        if self.cache_is_fresh(now):
            cached = self._cached
            assert cached is not None
            return cached
        result: TimingResult = await self.run(
            market_snapshot, event_id=event_id, candidate=candidate
        )
        result.fetched_at = now
        # A pessimistic fallback is never cached: a failure must not block
        # the market verdict for the whole window.
        if "agent_failure" not in result.anomalies:
            self._cached = result
        return result

    def invalidate(self) -> None:
        """Drop the cached verdict. The next ``get`` calls Grok again."""
        self._cached = None
