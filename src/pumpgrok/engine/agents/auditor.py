"""Wallet-audit agent: what the aggregates hide, on the fast model.

Port of the retired oracle ``src/agents/auditor.py`` with the prompt
translated to English. Metrics see shares, counts, and averages; the
auditor reads the raw trade stream and holder list for coordinated buying,
wash trading, creator dump preparation, bundled launches, and the organic
buyer share. Skeptical by design: thin data sets a flag and lowers
confidence instead of excusing the token.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, ClassVar

from pumpgrok.core.units import lamports_to_sol
from pumpgrok.engine.agents.base import JSON_ONLY, GrokAgent
from pumpgrok.engine.models import AuditResult, Holder, Token, TokenMetrics, Trade

AUDITOR_PROMPT = f"""You are a forensic analyst of on-chain activity on
pump.fun. You get the raw trades and the holder list of a new memecoin.
Your job is to find the manipulation that aggregated metrics cannot see.

Look specifically for:
1. Coordinated buying: close-sized amounts, gaps between buys under
   5 seconds, a repeating rhythm, wallets with a shared funding source or
   sequential addresses.
2. Wash trading: the same wallet buying and selling, circular volume,
   volume with no growth in unique holders.
3. Creator dump preparation: the creator topping up from other addresses,
   concentration in linked wallets, splitting a position before the exit.
4. Bundled launch: buys in the same block or in the first second of the
   token's life from several addresses at once.
5. The organic buyer share: buyers who fit none of the patterns above.

Be skeptical. When data is thin, set the flag to true and lower the
confidence instead of excusing the token.

Answer format:
{{
  "coordinated_buying": true|false,
  "wash_trading": true|false,
  "creator_dump_prep": true|false,
  "bundled_launch": true|false,
  "organic_buyer_share": 0.0-1.0,
  "confidence": 0.0-1.0,
  "flags": ["short labels for what was found"],
  "reasoning": "2-3 sentences with specifics: addresses, amounts, gaps"
}}

{JSON_ONLY}"""


class AuditorAgent(GrokAgent):
    """Forensic wallet analyst on the fast model."""

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
                "age_seconds": round(token.age_seconds(self._clock.now())),
                "curve_progress": round(token.curve_progress, 4),
            },
            "trades": [
                {
                    "wallet": trade.wallet,
                    "side": "buy" if trade.is_buy else "sell",
                    "sol": str(lamports_to_sol(Decimal(trade.sol_amount))),
                    "t": round(trade.timestamp - token.created_timestamp, 2)
                    if token.created_timestamp
                    else trade.timestamp,
                    "slot": trade.slot,
                }
                for trade in trades
            ],
            "holders": [
                {
                    "address": holder.address,
                    "share": round(holder.share, 5),
                    "is_creator": holder.is_creator,
                }
                for holder in holders
            ],
        }
        if metrics is not None:
            payload["computed_metrics"] = metrics.model_dump()
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def fallback(self, reason: str) -> AuditResult:
        return AuditResult.pessimistic(reason)
