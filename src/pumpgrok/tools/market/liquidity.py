"""market.liquidity: pool depth from the ASSUMED curve account (TOOL-001, B9).

Reads the same curve account as ``market.price`` through
:mod:`pumpgrok.tools.onchain.curve_layout`; ``liquidity_lamports`` is the
virtual SOL reserve. Impact math is a plain constant-product share
``size / (reserves + size)`` evaluated in Decimal.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.curve_layout import (
    CurveDecodeError,
    curve_progress,
    decode_curve_account_base64,
)
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


class LiquidityIn(ToolInput):
    """Depth for ``mint`` plus impact for a hypothetical order size."""

    mint: MintStr
    curve_account: MintStr
    order_size_lamports: int = Field(default=0, ge=0)


class LiquidityOut(ToolOutput):
    """Reserves and impact ratios; ``graduated`` mirrors the curve flag."""

    virtual_sol_reserves_lamports: int = Field(ge=0)
    virtual_token_reserves_units: int = Field(ge=0)
    liquidity_lamports: int = Field(ge=0)
    curve_progress: Decimal = Field(ge=0, le=1)
    price_impact: Decimal = Field(ge=0)
    order_to_liquidity_ratio: Decimal = Field(ge=0)
    graduated: bool


LIQUIDITY_SPEC = ToolSpec(
    name="market.liquidity",
    description=(
        "Pool depth from the on-chain bonding-curve reserves (ASSUMED "
        "layout) with price impact for a given order size."
    ),
    input_model=LiquidityIn,
    output_model=LiquidityOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    retry=J4,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/curve_layout.py via solana_rpc getAccountInfo",
)


async def run_liquidity(inp: LiquidityIn, rpc: RpcClient) -> dict[str, Any]:
    """Fetch the curve account and return a validated ``LiquidityOut`` payload."""
    try:
        result = await rpc.call("getAccountInfo", [inp.curve_account, {"encoding": "base64"}])
    except RpcError as exc:
        raise DataStale(f"market.liquidity upstream failed mint={inp.mint}") from exc
    if not isinstance(result, dict) or result.get("value") is None:
        raise DataStale(f"market.liquidity account missing mint={inp.mint}")
    try:
        state = decode_curve_account_base64(result["value"].get("data"))
    except CurveDecodeError as exc:
        raise DataStale(f"market.liquidity undecodable curve mint={inp.mint}") from exc
    vsol = Decimal(state.virtual_sol_reserves_lamports)
    order = Decimal(inp.order_size_lamports)
    impact = order / (vsol + order) if order > 0 else Decimal(0)
    token_reserves_units = state.virtual_token_reserves_units
    out = {
        "virtual_sol_reserves_lamports": state.virtual_sol_reserves_lamports,
        "virtual_token_reserves_units": token_reserves_units,  # pragma: allowlist secret: field
        "liquidity_lamports": state.virtual_sol_reserves_lamports,
        "curve_progress": curve_progress(state),
        "price_impact": impact,
        "order_to_liquidity_ratio": order / vsol if vsol > 0 else Decimal(0),
        "graduated": state.complete,
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
            rpc.clock,
        ),
    }
    return LiquidityOut.model_validate(out).model_dump()


def build_liquidity_tool(rpc: RpcClient) -> Tool:
    """Bind ``market.liquidity`` to one injected RPC client (no globals)."""

    @tool(LIQUIDITY_SPEC)
    async def _liquidity(payload: LiquidityIn) -> dict[str, Any]:
        return await run_liquidity(payload, rpc)

    return _liquidity
