"""Whale seat behind the gateway (GRK-05).

Routes every Grok call through the single gateway entry from `grok/__init__`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pumpgrok.grok import GatewayRequest

if TYPE_CHECKING:
    from pumpgrok.grok import GatewayResponse, GrokGateway

PROMPT = "Summarize whale flow as JSON with keys score, reason."


class WhaleSeat:
    agent = "whale"

    async def run(
        self,
        gateway: GrokGateway,
        *,
        consequence_id: str,
        prompt_body: str,
        score: int,
    ) -> GatewayResponse | None:

        return await gateway.call(
            GatewayRequest(
                agent=self.agent,
                prompt=f"{PROMPT} {prompt_body}",
                consequence_id=consequence_id,
                score=score,
            )
        )
