"""Scout seat behind the gateway (GRK-05).

Routes every Grok call through the single gateway entry from `grok/__init__`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pumpgrok.grok import GatewayResponse, GrokGateway

PROMPT = "Discover candidates and score them as JSON with keys score, reason."


class ScoutSeat:
    agent = "scout"

    async def run(
        self,
        gateway: GrokGateway,
        *,
        consequence_id: str,
        prompt_body: str,
        score: int,
    ) -> GatewayResponse | None:
        from pumpgrok.grok import GatewayRequest

        return await gateway.call(
            GatewayRequest(
                agent=self.agent,
                prompt=f"{PROMPT} {prompt_body}",
                consequence_id=consequence_id,
                score=score,
            )
        )
