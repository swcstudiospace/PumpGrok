"""onchain.priority_fee: fee estimate with an enforced cap (TOOL-002).

Wraps the ported :func:`pumpgrok.tools.onchain.priority_fee.estimate_priority_fee`
without editing it (characterization pins); the wrapper converts the
Decimal multiplier at the boundary and enforces ``max_micro_lamports``
(the cap the oracle documents but does not apply). ``accounts`` is
accepted for catalog compatibility but the ported oracle samples
globally, so differing account lists yield the same estimate.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, meta_now
from pumpgrok.tools.onchain.priority_fee import estimate_priority_fee
from pumpgrok.tools.onchain.rpc import RpcClient


class PriorityFeeIn(ToolInput):
    """Fee estimate knobs; ``accounts`` is accepted but sampled globally."""

    percentile: int = Field(default=50, ge=0, le=100)
    multiplier: Decimal = Field(default=Decimal("1.2"), ge=1, le=3)
    max_micro_lamports: int = Field(default=50000, ge=0)
    accounts: list[str] = Field(default_factory=list)


class PriorityFeeOut(ToolOutput):
    """Capped estimate with the cap flag."""

    samples: int = Field(ge=0)
    median: int = Field(ge=0)
    percentile_fee: int = Field(ge=0)
    recommended_micro_lamports: int = Field(ge=0)
    capped: bool


PRIORITY_FEE_SPEC = ToolSpec(
    name="onchain.priority_fee",
    description=(
        "Prioritization-fee estimate from recent fees with a "
        "caller-supplied cap; sampling is global."
    ),
    input_model=PriorityFeeIn,
    output_model=PriorityFeeOut,
    side_effect=SideEffect.READ,
    timeout_s=15.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/priority_fee.py estimate_priority_fee",
)


async def run_priority_fee(inp: PriorityFeeIn, rpc: RpcClient) -> dict[str, Any]:
    """Wrap the ported estimator and return a validated typed payload."""
    result = await estimate_priority_fee(
        rpc, percentile=inp.percentile, multiplier=float(inp.multiplier)
    )
    if not result.get("ok"):
        raise DataStale("onchain.priority_fee upstream failed")
    try:
        computed = int(result["recommended_micro_lamports"])
        samples = int(result["samples"])
        median = int(result["median"])
        percentile_fee = int(result["percentile_fee"])
    except (KeyError, ValueError, TypeError) as exc:
        raise DataStale("onchain.priority_fee malformed") from exc
    out = {
        "samples": samples,
        "median": median,
        "percentile_fee": percentile_fee,
        "recommended_micro_lamports": min(computed, inp.max_micro_lamports),
        "capped": computed > inp.max_micro_lamports,
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return PriorityFeeOut.model_validate(out).model_dump()


def build_priority_fee_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.priority_fee`` to one injected RPC client."""

    @tool(PRIORITY_FEE_SPEC)
    async def _priority_fee(payload: PriorityFeeIn) -> dict[str, Any]:
        return await run_priority_fee(payload, rpc)

    return _priority_fee
