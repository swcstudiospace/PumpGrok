"""market.price: bonding-curve spot price over Solana RPC (TOOL-001, B9).

Reads the curve account with ``getAccountInfo`` (base64) and decodes it with
the ASSUMED layout in :mod:`pumpgrok.tools.onchain.curve_layout`. No REST
fallback and no Jupiter quote path exist in this module (R44, R46, R47).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.curve_layout import (
    CurveDecodeError,
    curve_market_cap_lamports,
    curve_price_sol_per_token,
    curve_progress,
    decode_curve_account_base64,
)
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


class PriceIn(ToolInput):
    """Price for ``mint`` read from the curve account at ``curve_account``."""

    mint: MintStr
    curve_account: MintStr


class PriceOut(ToolOutput):
    """SOL per token with curve context; ``source`` is always ``curve``."""

    price: Decimal
    source: Literal["curve"]
    curve_progress: Decimal = Field(ge=0, le=1)
    market_cap_lamports: int = Field(ge=0)
    graduated: bool
    context_slot: int | None = None


PRICE_SPEC = ToolSpec(
    name="market.price",
    description=(
        "Spot price of a token in SOL from the on-chain bonding-curve "
        "reserves (ASSUMED layout); the only price the fill model uses."
    ),
    input_model=PriceIn,
    output_model=PriceOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    retry=J4,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/curve_layout.py via solana_rpc getAccountInfo",
)


async def run_price(inp: PriceIn, rpc: RpcClient) -> dict[str, Any]:
    """Fetch the curve account and return a validated ``PriceOut`` payload."""
    try:
        result = await rpc.call("getAccountInfo", [inp.curve_account, {"encoding": "base64"}])
    except RpcError as exc:
        raise DataStale(f"market.price upstream failed mint={inp.mint}") from exc
    if not isinstance(result, dict) or result.get("value") is None:
        raise DataStale(f"market.price account missing mint={inp.mint}")
    value = result["value"]
    try:
        state = decode_curve_account_base64(value.get("data"))
    except CurveDecodeError as exc:
        raise DataStale(f"market.price undecodable curve mint={inp.mint}") from exc
    context = result.get("context")
    slot = context.get("slot") if isinstance(context, dict) else None
    ambient = ambient_correlation()
    out = {
        "price": curve_price_sol_per_token(state),
        "source": "curve",
        "curve_progress": curve_progress(state),
        "market_cap_lamports": curve_market_cap_lamports(state),
        "graduated": state.complete,
        "context_slot": slot,
        "meta": meta_now(
            SOLANA_RPC_SOURCE, inp.correlation_id or (str(ambient) if ambient else None)
        ),
    }
    return PriceOut.model_validate(out).model_dump()


def build_price_tool(rpc: RpcClient) -> Tool:
    """Bind ``market.price`` to one injected RPC client (no globals)."""

    @tool(PRICE_SPEC)
    async def _price(payload: PriceIn) -> dict[str, Any]:
        return await run_price(payload, rpc)

    return _price
