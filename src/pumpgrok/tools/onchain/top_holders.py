"""onchain.top_holders: concentration against total supply (TOOL-002).

Wraps the ported :func:`pumpgrok.tools.onchain.holders.holder_snapshot`
without editing it (characterization pins); the wrapper converts the
float sample amounts to base-unit ints and divides by the ``getTokenSupply``
total, so shares are against supply, not against the sample. ``owner``
stays null: largest-accounts entries carry no owner without extra calls.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


class HolderRow(BaseModel):
    """One holder with a 0..1 share of total supply."""

    model_config = ConfigDict(frozen=True)

    address: str
    owner: str | None = None
    amount_units: int = Field(ge=0)
    share: Decimal = Field(ge=0, le=1)


class TopHoldersIn(ToolInput):
    """Concentration for ``mint`` excluding ``exclude`` (curve/LP accounts)."""

    mint: MintStr
    limit: int = Field(default=20, ge=1, le=20)
    exclude: list[str] = Field(default_factory=list)


class TopHoldersOut(ToolOutput):
    """Supply-based concentration with the excluded accounts echoed."""

    holders: list[HolderRow]
    top1_share: Decimal = Field(ge=0, le=1)
    top5_share: Decimal = Field(ge=0, le=1)
    top10_share: Decimal = Field(ge=0, le=1)
    supply_units: int = Field(ge=0)
    excluded: list[str] = Field(default_factory=list)


TOP_HOLDERS_SPEC = ToolSpec(
    name="onchain.top_holders",
    description=(
        "Largest token accounts with shares against total supply and "
        "curve/LP accounts excluded; owners stay unresolved."
    ),
    input_model=TopHoldersIn,
    output_model=TopHoldersOut,
    side_effect=SideEffect.READ,
    timeout_s=15.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/holders.py holder_snapshot + getTokenSupply",
)


async def run_top_holders(inp: TopHoldersIn, rpc: RpcClient) -> dict[str, Any]:
    """Wrap the ported snapshot and return a validated typed payload."""
    snap = await holder_snapshot(inp.mint, rpc, limit=inp.limit)
    if not snap.get("ok"):
        raise DataStale(f"onchain.top_holders snapshot failed mint={inp.mint}")
    try:
        supply_res = await rpc.call("getTokenSupply", [inp.mint])
    except RpcError as exc:
        raise DataStale(f"onchain.top_holders supply failed mint={inp.mint}") from exc
    try:
        supply = int(supply_res["value"]["amount"])
    except (KeyError, ValueError, TypeError) as exc:
        raise DataStale(f"onchain.top_holders supply malformed mint={inp.mint}") from exc
    if supply <= 0:
        raise DataStale(f"onchain.top_holders zero supply mint={inp.mint}")
    excluded = set(inp.exclude)
    rows: list[HolderRow] = []
    try:
        for entry in snap["holders"]:
            address = str(entry["address"])
            if address in excluded:
                continue
            amount = int(Decimal(str(entry["uiAmount"])) * (10 ** int(entry["decimals"])))
            rows.append(
                HolderRow(
                    address=address,
                    owner=None,
                    amount_units=amount,
                    share=Decimal(amount) / Decimal(supply),
                )
            )
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        raise DataStale(f"onchain.top_holders snapshot malformed mint={inp.mint}") from exc
    rows.sort(key=lambda r: r.amount_units, reverse=True)

    def _share(n: int) -> Decimal:
        return min(Decimal(1), sum((r.share for r in rows[:n]), Decimal(0)))

    out = {
        "holders": [r.model_dump() for r in rows],
        "top1_share": _share(1),
        "top5_share": _share(5),
        "top10_share": _share(10),
        "supply_units": supply,
        "excluded": sorted(excluded),
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return TopHoldersOut.model_validate(out).model_dump()


def build_top_holders_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.top_holders`` to one injected RPC client."""

    @tool(TOP_HOLDERS_SPEC)
    async def _top_holders(payload: TopHoldersIn) -> dict[str, Any]:
        return await run_top_holders(payload, rpc)

    return _top_holders
