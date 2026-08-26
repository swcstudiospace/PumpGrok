#!/usr/bin/env python3
"""
authority_check.py – Check mint authority, freeze authority, and basic Token-2022 flags.

Usage:
  python tools/authority_check.py --mint <mint_address> [--rpc <rpc_url>]

Outputs clean JSON. Never signs or sends.
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

DEFAULT_RPC = "https://api.mainnet-beta.solana.com"


def rpc_call(rpc_url: str, method: str, params: list) -> Dict[str, Any]:
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


def check_mint(mint: str, rpc_url: str) -> Dict[str, Any]:
    try:
        result = rpc_call(rpc_url, "getAccountInfo", [
            mint,
            {"encoding": "jsonParsed"}
        ])

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
            "rpc": rpc_url,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "mint": mint}


def main():
    parser = argparse.ArgumentParser(description="Authority check helper for PumpGrok RISK")
    parser.add_argument("--mint", required=True, help="Token mint address")
    parser.add_argument("--rpc", default=DEFAULT_RPC, help="Solana RPC URL")
    args = parser.parse_args()

    result = check_mint(args.mint, args.rpc)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
