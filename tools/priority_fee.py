#!/usr/bin/env python3
"""
priority_fee.py – Estimate Solana prioritization fees for PumpGrok.

Usage:
  python tools/priority_fee.py [--rpc <rpc_url>] [--percentile 50] [--multiplier 1.2]

Outputs clean JSON with median / percentile fee in micro-lamports per compute unit.
Never signs or sends.
"""

import argparse
import json
import statistics
import sys
from typing import Any, Dict, List

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests library required. Run: pip install requests"}))
    sys.exit(1)

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def rpc_call(rpc_url: str, method: str, params: list) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    resp = requests.post(rpc_url, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("result")


def estimate_priority_fee(rpc_url: str, percentile: int = 50, multiplier: float = 1.2) -> Dict[str, Any]:
    try:
        # getRecentPrioritizationFees returns a list of {slot, prioritizationFee}
        result = rpc_call(rpc_url, "getRecentPrioritizationFees", [[]])
        if not result:
            return {"ok": False, "error": "Empty prioritization fee response"}

        fees: List[int] = [item.get("prioritizationFee", 0) for item in result if isinstance(item, dict)]
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
            "recommended_lamports_per_cu": recommended,  # alias
            "rpc": rpc_url,
            "note": "Value is micro-lamports per compute unit. Use with ComputeBudgetProgram.set_compute_unit_price.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description="Priority fee estimator for PumpGrok")
    parser.add_argument("--rpc", default=DEFAULT_RPC, help="Solana RPC URL")
    parser.add_argument("--percentile", type=int, default=50, help="Percentile to target (default 50 = median)")
    parser.add_argument("--multiplier", type=float, default=1.2, help="Safety multiplier on the chosen percentile (default 1.2)")
    args = parser.parse_args()

    result = estimate_priority_fee(args.rpc, args.percentile, args.multiplier)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
