"""onchain.token_metadata: mint fields over RPC (TOOL-002, B9, T-03-02-02).

Wraps the ported :func:`pumpgrok.tools.onchain.authorities.check_mint`
without editing it (characterization pins). Off-chain fields (name,
symbol, uri, socials, creator) stay null: RPC carries no token-2022
metadata pointer resolution in Phase 3, and enrichment over the GET-only
social client is composed by a later plan. Untrusted by construction.
"""

from __future__ import annotations

from typing import Any, Literal

from pumpgrok.core.errors import DataStale
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.tools._common import J5, SOLANA_RPC_SOURCE, MintStr, meta_now
from pumpgrok.tools.onchain.authorities import check_mint
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


class TokenMetadataIn(ToolInput):
    """Mint account fields for ``mint``."""

    mint: MintStr


class TokenMetadataOut(ToolOutput):
    """On-chain mint fields; off-chain metadata stays null (RPC only)."""

    decimals: int
    supply: str
    is_initialized: bool
    program: Literal["spl-token", "token-2022"]
    extensions: list[str]
    name: str | None = None
    symbol: str | None = None
    uri: str | None = None
    twitter: str | None = None
    telegram: str | None = None
    website: str | None = None
    creator: str | None = None


TOKEN_METADATA_SPEC = ToolSpec(
    name="onchain.token_metadata",
    description=(
        "Mint account fields (decimals, supply, program, extensions) from "
        "parsed account data; off-chain metadata stays null."
    ),
    input_model=TokenMetadataIn,
    output_model=TokenMetadataOut,
    side_effect=SideEffect.READ,
    timeout_s=15.0,
    retry=J5,
    rate_limit_key=SOLANA_RPC_SOURCE,
    backend="src/pumpgrok/tools/onchain/authorities.py check_mint",
)


TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # noqa: S105  # public SPL program id, not a credential
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105  # public Token-2022 program id, not a credential
_PROGRAM_BY_OWNER: dict[str, Literal["spl-token", "token-2022"]] = {
    TOKEN_PROGRAM_ID: "spl-token",
    TOKEN_2022_PROGRAM_ID: "token-2022",
}


def _extension_name(entry: object) -> str:
    """Extension name from a jsonParsed entry ``{"extension": name, "state": {...}}``."""
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        name = entry.get("extension")
        if isinstance(name, str):
            return name
    raise ValueError("unrecognised token-2022 extension entry")


async def _program(mint: str, rpc: RpcClient) -> Literal["spl-token", "token-2022"]:
    """Token program from the mint account owner; extension presence does not decide it."""
    try:
        account = await rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        program = _PROGRAM_BY_OWNER.get(account["value"]["owner"])
    except (RpcError, DataStale, KeyError, TypeError) as exc:
        raise DataStale(f"onchain.token_metadata owner failed mint={mint}") from exc
    if program is None:
        raise DataStale(f"onchain.token_metadata owner is not a token program mint={mint}")
    return program


async def run_token_metadata(inp: TokenMetadataIn, rpc: RpcClient) -> dict[str, Any]:
    """Wrap the ported mint check and return a validated typed payload."""
    result = await check_mint(inp.mint, rpc)
    if not result.get("ok"):
        raise DataStale(f"onchain.token_metadata upstream failed mint={inp.mint}")
    try:
        decimals = int(result["decimals"])
        supply = str(result["supply"])
        initialized = bool(result["isInitialized"])
        extensions = [_extension_name(e) for e in (result.get("extensions") or [])]
    except (KeyError, ValueError, TypeError) as exc:
        raise DataStale(f"onchain.token_metadata malformed mint={inp.mint}") from exc
    program = await _program(inp.mint, rpc)
    out = {
        "decimals": decimals,
        "supply": supply,
        "is_initialized": initialized,
        "program": program,
        "extensions": extensions,
        "name": None,
        "symbol": None,
        "uri": None,
        "twitter": None,
        "telegram": None,
        "website": None,
        "creator": None,
        "meta": meta_now(
            SOLANA_RPC_SOURCE,
            inp.correlation_id or (str(a) if (a := ambient_correlation()) else None),
            rpc.clock,
        ),
    }
    return TokenMetadataOut.model_validate(out).model_dump()


def build_token_metadata_tool(rpc: RpcClient) -> Tool:
    """Bind ``onchain.token_metadata`` to one injected RPC client."""

    @tool(TOKEN_METADATA_SPEC)
    async def _token_metadata(payload: TokenMetadataIn) -> dict[str, Any]:
        return await run_token_metadata(payload, rpc)

    return _token_metadata
