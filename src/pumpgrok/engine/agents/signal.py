"""Signal seat behind the gateway (GRK-05, T-14-02-01).

The seat calls the gateway with an event consequence id. It never reaches
for the vendor agent directly; direct transport calls live only in `grok/`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pumpgrok.grok import GatewayRequest

if TYPE_CHECKING:
    from pumpgrok.grok import GatewayResponse, GrokGateway

PROMPT = "Score the candidate event as JSON with keys score, reason."


class SignalSeat:
    """Event-consequence entry for the signal seat."""

    agent = "signal"

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
