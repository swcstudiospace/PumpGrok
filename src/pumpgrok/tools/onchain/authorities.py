"""Mint authority check over :class:`RpcClient` (STRUCT-002).

Port of the retired ``authority_check`` root oracle ``check_mint``. Output keys are
byte-identical to the oracle except the ``rpc`` URL echo is dropped: the
endpoint URL must never leave the client boundary (T-02-01).
"""

from __future__ import annotations

from typing import Any

from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


async def check_mint(mint: str, rpc: RpcClient) -> dict[str, Any]:
    """Return authority flags for ``mint``; ``ok: False`` when absent or on error."""
    try:
        result = await rpc.call("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
        if result is None or result.get("value") is None:
            return {"ok": False, "error": "Mint account not found or not a token mint"}

        value = result["value"]
        data = value.get("data", {})
        parsed = data.get("parsed", {}) if isinstance(data, dict) else {}
        info = parsed.get("info", {})

        mint_authority = info.get("mintAuthority")
        freeze_authority = info.get("freezeAuthority")
        decimals = info.get("decimals")
        supply = info.get("supply")
        is_initialized = info.get("isInitialized")
        if decimals is None or is_initialized is None:
            return {"ok": False, "error": "Mint account not found or not a token mint"}
        extensions = info.get("extensions") or []

        return {
            "ok": True,
            "mint": mint,
            "mintAuthority": mint_authority,
            "freezeAuthority": freeze_authority,
            "decimals": decimals,
            "supply": supply,
            "isInitialized": is_initialized,
            "extensions": extensions,
            "hasMintAuthority": mint_authority is not None,
            "hasFreezeAuthority": freeze_authority is not None,
        }
    except RpcError as exc:
        return {"ok": False, "error": str(exc), "mint": mint}
    except Exception:
        return {"ok": False, "error": "authority check failed", "mint": mint}
