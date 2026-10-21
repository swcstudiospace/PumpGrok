"""onchain.lp_status: curve completion from the ASSUMED account (TOOL-002, B9).

Reads the same curve account as ``market.price`` through
:mod:`pumpgrok.tools.onchain.curve_layout` (never REST). LP-mint fields
stay null: no graduated-pool data source is wired in Phase 3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.curve_layout import (
    CurveDecodeError,
    decode_curve_account_base64,
)
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


class LpStatusIn(ToolInput):
    """Liquidity stage for ``mint`` from its curve account."""

    mint: MintStr
    curve_account: MintStr


class LpStatusOut(ToolOutput):
    """Stage plus completion flag; LP-mint fields are unwired (null)."""

    stage: Literal["bonding_curve", "graduated", "unknown"]
    curve_complete: bool | None = None
    lp_mint: str | None = None
    lp_burned_pct: float | None = None
    lp_locked_pct: float | None = None
    locker: str | None = None
    lock_expires_at: datetime | None = None
    checked: list[str] = []


LP_STATUS_SPEC = ToolSpec(
    name="onchain.lp_status",
    description=(
        "Liquidity stage from the on-chain bonding-curve account "
        "(ASSUMED layout); LP-mint lock fields are unwired."
    ),
    input_model=LpStatusIn,
    output_model=LpStatusOut,
    side_effect=SideEffect.READ,
    timeout_s=20.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/curve_layout.py via solana_rpc getAccountInfo",
)


async def run_lp_status(inp: LpStatusIn, rpc: RpcClient) -> dict:
    """Fetch the curve account and return a validated ``LpStatusOut`` payload."""
    try:
        result = await rpc.call("getAccountInfo", [inp.curve_account, {"encoding": "base64"}])
    except RpcError as exc:
        raise DataStale(f"onchain.lp_status upstream failed mint={inp.mint}") from exc
    if not isinstance(result, dict) or result.get("value") is None:
        raise DataStale(f"onchain.lp_status account missing mint={inp.mint}")
    try:
        state = decode_curve_account_base64(result["value"].get("data"))
    except CurveDecodeError as exc:
        raise DataStale(f"onchain.lp_status undecodable curve mint={inp.mint}") from exc
    out = {
        "stage": "graduated" if state.complete else "bonding_curve",
        "curve_complete": state.complete,
        "lp_mint": None,
        "lp_burned_pct": None,
        "lp_locked_pct": None,
        "locker": None,
        "lock_expires_at": None,
        "checked": ["curve_account"],
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return LpStatusOut.model_validate(out).model_dump()


def build_lp_status_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.lp_status`` to one injected RPC client."""

    @tool(LP_STATUS_SPEC)
    async def _lp_status(payload: LpStatusIn) -> dict:
        return await run_lp_status(payload, rpc)

    return _lp_status
