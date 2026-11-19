"""Top-holder concentration snapshot over :class:`RpcClient` (STRUCT-002).

Verbatim port of the retired ``holder_check`` root oracle ``holder_snapshot``, including the
sampled-only disclosure ``note`` byte-identical. Uses
``getTokenLargestAccounts`` on public RPC (R47).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pumpgrok.core.errors import DataStale
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError

# Payload shapes the holder parser cannot walk; each becomes a failed check.
_MALFORMED = (ArithmeticError, AttributeError, KeyError, TypeError, ValueError)


def _ui_amount(item: dict[str, Any]) -> Decimal:
    """UI amount of one largest account; a missing or null amount is malformed, not zero."""
    raw = item.get("uiAmount")
    if raw is None:
        raise ValueError("holder uiAmount missing")
    amount = Decimal(str(float(raw)))
    if not amount.is_finite():
        raise ValueError("holder uiAmount not finite")
    return amount


def _top_share_pct(amounts: list[Decimal], total: Decimal, count: int) -> float:
    """Percent of the sampled supply held by the largest ``count`` accounts."""
    if not total:
        return 0.0
    return round(float(sum(amounts[:count], Decimal(0)) / total * 100), 2)


async def holder_snapshot(mint: str, rpc: RpcClient, limit: int = 20) -> dict[str, Any]:
    """Return concentration stats over the largest accounts sample."""
    try:
        result = await rpc.call("getTokenLargestAccounts", [mint])
        value = result.get("value") if isinstance(result, dict) else result
        if not value:
            return {"ok": False, "error": "No largest accounts returned", "mint": mint}

        sample = value[:limit]
        amounts = [_ui_amount(item) for item in sample]
        total = sum(amounts, Decimal(0))
        holders: list[dict[str, Any]] = [
            {
                "address": item.get("address"),
                "uiAmount": float(amount),
                "decimals": item.get("decimals"),
            }
            for item, amount in zip(sample, amounts, strict=True)
        ]

        # Simple concentration metrics (note: does not exclude LP automatically)
        return {
            "ok": True,
            "mint": mint,
            "holderCountReturned": len(holders),
            "totalUiAmountSampled": float(total),
            "top1Pct": _top_share_pct(amounts, total, 1),
            "top5Pct": _top_share_pct(amounts, total, 5),
            "top10Pct": _top_share_pct(amounts, total, 10),
            "holders": holders,
            "note": (
                "Percentages are of the sampled largest accounts only. "
                "LP and locked tokens are not auto-excluded. "
                "Cross-check with Solscan / gmgn for production decisions."
            ),
        }
    except (RpcError, DataStale) as exc:
        return {"ok": False, "error": str(exc), "mint": mint}
    except _MALFORMED:
        return {"ok": False, "error": "holder check failed", "mint": mint}
