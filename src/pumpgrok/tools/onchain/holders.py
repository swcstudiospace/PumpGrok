"""Top-holder concentration snapshot over :class:`RpcClient` (STRUCT-002).

Verbatim port of the retired ``holder_check`` root oracle ``holder_snapshot``, including the
sampled-only disclosure ``note`` byte-identical. Uses
``getTokenLargestAccounts`` on public RPC (R47).
"""

from __future__ import annotations

from typing import Any

from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


async def holder_snapshot(mint: str, rpc: RpcClient, limit: int = 20) -> dict[str, Any]:
    """Return concentration stats over the largest accounts sample."""
    try:
        result = await rpc.call("getTokenLargestAccounts", [mint])
        value = result.get("value") if isinstance(result, dict) else result
        if not value:
            return {"ok": False, "error": "No largest accounts returned", "mint": mint}

        holders: list[dict[str, Any]] = []
        total_ui = 0.0
        for item in value[:limit]:
            ui = float(item.get("uiAmount") or 0)
            total_ui += ui
            holders.append(
                {
                    "address": item.get("address"),
                    "uiAmount": ui,
                    "decimals": item.get("decimals"),
                }
            )

        # Simple concentration metrics (note: does not exclude LP automatically)
        top1 = holders[0]["uiAmount"] / total_ui if holders and total_ui else 0
        top5 = sum(h["uiAmount"] for h in holders[:5]) / total_ui if total_ui else 0
        top10 = sum(h["uiAmount"] for h in holders[:10]) / total_ui if total_ui else 0

        return {
            "ok": True,
            "mint": mint,
            "holderCountReturned": len(holders),
            "totalUiAmountSampled": total_ui,
            "top1Pct": round(top1 * 100, 2),
            "top5Pct": round(top5 * 100, 2),
            "top10Pct": round(top10 * 100, 2),
            "holders": holders,
            "note": (
                "Percentages are of the sampled largest accounts only. "
                "LP and locked tokens are not auto-excluded. "
                "Cross-check with Solscan / gmgn for production decisions."
            ),
        }
    except RpcError as exc:
        return {"ok": False, "error": str(exc), "mint": mint}
    except Exception:
        return {"ok": False, "error": "holder check failed", "mint": mint}
