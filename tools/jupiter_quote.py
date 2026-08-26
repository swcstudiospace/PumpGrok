#!/usr/bin/env python3
"""
jupiter_quote.py – Get a structured Jupiter quote for PumpGrok.

Usage:
  python tools/jupiter_quote.py --input-mint <mint> --output-mint <mint> --amount <lamports> [--slippage-bps 100]

Outputs clean JSON to stdout. Never signs or sends.
"""

import argparse
import json
import sys
from typing import Any, Dict

try:
    import requests
except ImportError:
    print(json.dumps({"error": "requests library required. Run: pip install requests"}))
    sys.exit(1)

JUPITER_QUOTE_URL = "https://quote-api.jup.ag/v6/quote"


def get_quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int = 100) -> Dict[str, Any]:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(slippage_bps),
    }
    try:
        resp = requests.get(JUPITER_QUOTE_URL, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "ok": False}

    route = data.get("routePlan") or []
    return {
        "ok": True,
        "inputMint": data.get("inputMint"),
        "outputMint": data.get("outputMint"),
        "inAmount": data.get("inAmount"),
        "outAmount": data.get("outAmount"),
        "otherAmountThreshold": data.get("otherAmountThreshold"),
        "slippageBps": data.get("slippageBps"),
        "priceImpactPct": data.get("priceImpactPct"),
        "routePlan": [
            {
                "swapInfo": r.get("swapInfo", {}),
                "percent": r.get("percent"),
            }
            for r in route
        ],
        "contextSlot": data.get("contextSlot"),
        "timeTaken": data.get("timeTaken"),
        "raw": data,
    }


def main():
    parser = argparse.ArgumentParser(description="Jupiter quote helper for PumpGrok")
    parser.add_argument("--input-mint", required=True, help="Input mint address")
    parser.add_argument("--output-mint", required=True, help="Output mint address")
    parser.add_argument("--amount", required=True, type=int, help="Amount in smallest units (lamports for SOL)")
    parser.add_argument("--slippage-bps", type=int, default=100, help="Slippage in basis points (default 100 = 1%)")
    args = parser.parse_args()

    result = get_quote(args.input_mint, args.output_mint, args.amount, args.slippage_bps)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
