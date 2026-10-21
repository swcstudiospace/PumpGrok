"""market.holders_snapshot: sampled holder view from RPC (TOOL-001, B9).

Wraps the ported :func:`pumpgrok.tools.onchain.holders.holder_snapshot`
without editing it (characterization pins); the wrapper converts the
float percentages to Decimal ratios at the boundary. Counts are of the
sampled largest accounts only; on-chain truth is ``onchain.top_holders``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J4, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.rpc import RpcClient


class HolderShare(BaseModel):
    """One sampled holder with a 0..1 share of the sample."""

    model_config = ConfigDict(frozen=True)

    wallet: str
    share: Decimal = Field(ge=0, le=1)


class HoldersSnapshotIn(ToolInput):
    """Sampled holder view for ``mint`` over the largest accounts."""

    mint: MintStr
    limit: int = Field(default=50, ge=1, le=50)


class HoldersSnapshotOut(ToolOutput):
    """Sampled shares; ``creator`` stays unresolved in this view."""

    holder_count: int = Field(ge=0)
    holders: list[HolderShare]
    top5_share: Decimal = Field(ge=0, le=1)
    creator_share: Decimal = Field(ge=0, le=1)
    creator: str | None = None


HOLDERS_SNAPSHOT_SPEC = ToolSpec(
    name="market.holders_snapshot",
    description=(
        "Sampled holder count and share distribution from the largest "
        "accounts; the creator is unresolved in this view."
    ),
    input_model=HoldersSnapshotIn,
    output_model=HoldersSnapshotOut,
    side_effect=SideEffect.READ,
    timeout_s=10.0,
    retry=J4,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/holders.py holder_snapshot",
)


async def run_holders_snapshot(inp: HoldersSnapshotIn, rpc: RpcClient) -> dict[str, Any]:
    """Wrap the ported snapshot and return a validated typed payload."""
    snap = await holder_snapshot(inp.mint, rpc, limit=inp.limit)
    if not snap.get("ok"):
        raise DataStale(f"market.holders_snapshot upstream failed mint={inp.mint}")
    try:
        total = Decimal(str(snap["totalUiAmountSampled"]))
        holders = [
            HolderShare(
                wallet=str(entry["address"]),
                share=(Decimal(str(entry["uiAmount"])) / total if total > 0 else Decimal(0)),
            )
            for entry in snap["holders"]
        ]
        top5 = sum((h.share for h in holders[:5]), Decimal(0))
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        raise DataStale(f"market.holders_snapshot malformed mint={inp.mint}") from exc
    out = {
        "holder_count": len(holders),
        "holders": [h.model_dump() for h in holders],
        "top5_share": min(Decimal(1), top5),
        "creator_share": Decimal(0),
        "creator": None,
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
            rpc.clock,
        ),
    }
    return HoldersSnapshotOut.model_validate(out).model_dump()


def build_holders_snapshot_tool(rpc: RpcClient) -> Tool:
    """Bind ``market.holders_snapshot`` to one injected RPC client."""

    @tool(HOLDERS_SNAPSHOT_SPEC)
    async def _holders_snapshot(payload: HoldersSnapshotIn) -> dict[str, Any]:
        return await run_holders_snapshot(payload, rpc)

    return _holders_snapshot
