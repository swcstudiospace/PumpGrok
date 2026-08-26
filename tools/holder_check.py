#!/usr/bin/env python3
"""
holder_check.py – Basic top-holder / concentration snapshot for PumpGrok.

Usage:
  python tools/holder_check.py --mint <mint> [--rpc <url>] [--limit 20]

Uses getTokenLargestAccounts (public RPC). Returns structured concentration stats.
Never signs or sends. For richer smart-money labelling prefer gmgn / paid APIs later.
"""

import argparse
import json
import sys
from typing import Any, Dict, List

try:
    import requests
except ImportError:
    print(json.dumps({"ok": False, "error": "requests library required. Run: pip install requests"}))
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
        raise RuntimeError(str(data["error"]))
    return data.get("result")


def holder_snapshot(mint: str, rpc_url: str, limit: int = 20) -> Dict[str, Any]:
    try:
        result = rpc_call(rpc_url, "getTokenLargestAccounts", [mint])
        value = result.get("value") if isinstance(result, dict) else result
        if not value:
            return {"ok": False, "error": "No largest accounts returned", "mint": mint}

        holders: List[Dict[str, Any]] = []
        total_ui = 0.0
        for item in value[:limit]:
            ui = float(item.get("uiAmount") or 0)
            total_ui += ui
            holders.append({
                "address": item.get("address"),
                "uiAmount": ui,
                "decimals": item.get("decimals"),
            })

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
            "rpc": rpc_url,
            "note": "Percentages are of the sampled largest accounts only. LP and locked tokens are not auto-excluded. Cross-check with Solscan / gmgn for production decisions.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "mint": mint}


def main():
    parser = argparse.ArgumentParser(description="Holder concentration helper for PumpGrok")
    parser.add_argument("--mint", required=True)
    parser.add_argument("--rpc", default=DEFAULT_RPC)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    result = holder_snapshot(args.mint, args.rpc, args.limit)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
