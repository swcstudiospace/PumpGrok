"""exec.quote: route quote through the ExecutionAdapter (TOOL-004).

Informational only (route, priority, cross-check): pre-graduation fills are
computed from the bonding-curve reserves, never from this quote (R38). The
Jupiter quote path lives in the adapter, never in this tool (R44).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from pumpgrok.core.adapter import ExecutionAdapter
from pumpgrok.core.ids import Clock, ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, MintStr, meta_now

__all__ = [
    "QUOTE_SPEC",
    "QuoteIn",
    "QuoteOut",
    "build_quote_tool",
    "run_quote",
]


class QuoteIn(ToolInput):
    """Route quote for ``amount`` from ``input_mint`` to ``output_mint``."""

    input_mint: MintStr
    output_mint: MintStr
    amount: int = Field(gt=0)
    slippage_bps: int = Field(default=100, ge=0, le=10_000)


class QuoteOut(ToolOutput):
    """Adapter quote; unreachable in Phase 3 (kept for the Phase 4 backend)."""

    quote_id: str
    in_amount: int = Field(ge=0)
    out_amount: int = Field(ge=0)
    other_amount_threshold: int = Field(ge=0)
    price_impact: str
    route_plan: list[dict[str, Any]] = Field(default_factory=list)
    context_slot: int | None = None
    source: str = "jupiter"
    expires_at: datetime | None = None


QUOTE_SPEC = ToolSpec(
    name="exec.quote",
    description=(
        "Route quote for a swap through the ExecutionAdapter; informational only, "
        "never the fill price. Phase 3 delegates and surfaces not_yet_implemented."
    ),
    input_model=QuoteIn,
    output_model=QuoteOut,
    side_effect=SideEffect.READ,
    timeout_s=12.0,
    retry=J4,
    rate_limit_key="jupiter",
    backend="pumpgrok.execution.paper_adapter.PaperAdapter.quote",
)


async def run_quote(inp: QuoteIn, adapter: ExecutionAdapter, clock: Clock) -> dict[str, Any]:
    """Delegate to the adapter (raises ``not_yet_implemented`` in Phase 3)."""
    quote = await adapter.quote(inp.input_mint, inp.output_mint, inp.amount, inp.slippage_bps)
    ambient = ambient_correlation()
    payload = quote.model_dump(mode="json")
    payload["price_impact"] = payload.pop("price_impact_pct")
    payload["meta"] = meta_now(
        "jupiter", inp.correlation_id or (str(ambient) if ambient else None), clock
    )
    return QuoteOut.model_validate(payload).model_dump()


def build_quote_tool(adapter: ExecutionAdapter, clock: Clock) -> Tool:
    """Bind ``exec.quote`` to one adapter and clock (no globals)."""

    @tool(QUOTE_SPEC)
    async def _quote(payload: QuoteIn) -> dict[str, Any]:
        return await run_quote(payload, adapter, clock)

    return _quote
