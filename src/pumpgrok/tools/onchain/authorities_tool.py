"""onchain.authorities: mint/freeze authority flags over RPC (TOOL-002).

Wraps the ported :func:`pumpgrok.tools.onchain.authorities.check_mint`
without editing it (characterization pins). ``slot`` stays null: the
ported oracle drops the ``context.slot`` echo, and this wrapper does not
re-fetch the account for a single field.
"""

from __future__ import annotations

from typing import Any

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.authorities import check_mint
from pumpgrok.tools.onchain.rpc import RpcClient


class AuthoritiesIn(ToolInput):
    """Authority flags for ``mint``."""

    mint: MintStr


class AuthoritiesOut(ToolOutput):
    """Mint/freeze authority presence; ``slot`` is unresolved (see module)."""

    mint_authority: str | None = None
    freeze_authority: str | None = None
    has_mint_authority: bool
    has_freeze_authority: bool
    slot: int | None = None


AUTHORITIES_SPEC = ToolSpec(
    name="onchain.authorities",
    description=(
        "Mint and freeze authority flags for a mint from parsed account "
        "data; the slot echo is unresolved in this wrapper."
    ),
    input_model=AuthoritiesIn,
    output_model=AuthoritiesOut,
    side_effect=SideEffect.READ,
    timeout_s=15.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/authorities.py check_mint",
)


async def run_authorities(inp: AuthoritiesIn, rpc: RpcClient) -> dict[str, Any]:
    """Wrap the ported mint check and return a validated typed payload."""
    result = await check_mint(inp.mint, rpc)
    if not result.get("ok"):
        raise DataStale(f"onchain.authorities upstream failed mint={inp.mint}")
    out = {
        "mint_authority": result.get("mintAuthority"),
        "freeze_authority": result.get("freezeAuthority"),
        "has_mint_authority": bool(result.get("hasMintAuthority")),
        "has_freeze_authority": bool(result.get("hasFreezeAuthority")),
        "slot": None,
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
        ),
    }
    return AuthoritiesOut.model_validate(out).model_dump()


def build_authorities_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.authorities`` to one injected RPC client."""

    @tool(AUTHORITIES_SPEC)
    async def _authorities(payload: AuthoritiesIn) -> dict[str, Any]:
        return await run_authorities(payload, rpc)

    return _authorities
