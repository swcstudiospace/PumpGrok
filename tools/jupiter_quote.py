#!/usr/bin/env python3
"""
jupiter_quote.py - Get a structured Jupiter quote for PumpGrok.

Usage:
  python tools/jupiter_quote.py --input-mint <mint> --output-mint <mint> --amount <lamports>
      [--slippage-bps 100]

Outputs clean JSON to stdout. Never signs or sends.
"""

import argparse
import json
import sys
from typing import Any

try:
    import requests
except ImportError:
    sys.stdout.write(
        json.dumps(
            {"ok": False, "error": "requests library required. Run: pip install requests"}
        )
        + "\n"
    )
    sys.exit(1)

JUPITER_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"


def get_quote(
    input_mint: str, output_mint: str, amount: int, slippage_bps: int = 100
) -> dict[str, Any]:
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
    parser.add_argument(
        "--amount", required=True, type=int, help="Amount in smallest units (lamports for SOL)"
    )
    parser.add_argument(
        "--slippage-bps",
        type=int,
        default=100,
        help="Slippage in basis points (default 100 = 1%)",
    )
    args = parser.parse_args()

    result = get_quote(args.input_mint, args.output_mint, args.amount, args.slippage_bps)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
