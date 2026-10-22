"""Prioritization-fee estimate over :class:`RpcClient` (STRUCT-002).

Port of the retired ``priority_fee`` root oracle ``estimate_priority_fee``: percentile math
is unchanged. ``recommended_lamports_per_cu`` is kept as an explicit alias
for ``recommended_micro_lamports`` (decision per MIGRATION_MAP row 77: keep
documented, never silently carried, never silently dropped).
"""

from __future__ import annotations

import statistics
from typing import Any

from pumpgrok.tools.onchain.rpc import RpcClient, RpcError


async def estimate_priority_fee(
    rpc: RpcClient, percentile: int = 50, multiplier: float = 1.2
) -> dict[str, Any]:
    """Estimate micro-lamports per compute unit from recent fees."""
    try:
        # getRecentPrioritizationFees returns a list of {slot, prioritizationFee}
        result = await rpc.call("getRecentPrioritizationFees", [[]])
        if not result:
            return {"ok": False, "error": "Empty prioritization fee response"}

        fees: list[int] = [
            item.get("prioritizationFee", 0) for item in result if isinstance(item, dict)
        ]
        fees = [f for f in fees if f is not None and f >= 0]

        if not fees:
            return {"ok": False, "error": "No valid fee samples"}

        fees_sorted = sorted(fees)
        n = len(fees_sorted)

        # Simple percentile
        idx = min(max(int(n * percentile / 100), 0), n - 1)
        pct_fee = fees_sorted[idx]
        median_fee = int(statistics.median(fees_sorted))
        mean_fee = int(statistics.mean(fees_sorted))
        max_fee = max(fees_sorted)
        min_fee = min(fees_sorted)

        recommended = int(pct_fee * multiplier)

        return {
            "ok": True,
            "samples": n,
            "min": min_fee,
            "median": median_fee,
            "mean": mean_fee,
            "max": max_fee,
            "percentile": percentile,
            "percentile_fee": pct_fee,
            "multiplier": multiplier,
            "recommended_micro_lamports": recommended,
            "recommended_lamports_per_cu": recommended,  # alias, see module docstring
            "note": (
                "Value is micro-lamports per compute unit. "
                "Use with ComputeBudgetProgram.set_compute_unit_price."
            ),
        }
    except RpcError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "priority fee estimate failed"}
