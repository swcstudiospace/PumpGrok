#!/usr/bin/env python3
"""
ticket_helper.py – Generate next PumpGrok ticket ID and optional proposal skeleton.

Usage:
  # Just get the next ticket ID
  python tools/ticket_helper.py next

  # Create a proposal skeleton file
  python tools/ticket_helper.py create --mint <mint> [--size <usd_or_sol>] [--slippage 100]

  # List recent proposal files
  python tools/ticket_helper.py list

Writes under /workspace/trading-desk/proposals/ when creating.
Never signs or sends.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

PROPOSALS_DIR = Path("/workspace/trading-desk/proposals")
# Fallback for local testing / when the desk folders are not yet created
if not PROPOSALS_DIR.parent.exists():
    PROPOSALS_DIR = Path("./trading-desk/proposals")


def ensure_dir() -> None:
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def list_existing_ids() -> List[str]:
    ensure_dir()
    ids = []
    for p in PROPOSALS_DIR.glob("SOL-*.md"):
        m = re.match(r"SOL-(\d{8})-(\d{3})", p.stem)
        if m:
            ids.append(p.stem)
    return sorted(ids)


def next_ticket_id() -> str:
    today = today_str()
    existing = list_existing_ids()
    today_ids = [i for i in existing if i.startswith(f"SOL-{today}-")]
    if not today_ids:
        seq = 1
    else:
        last = today_ids[-1]
        seq = int(last.split("-")[-1]) + 1
    return f"SOL-{today}-{seq:03d}"


def create_proposal(mint: str, size: Optional[str] = None, slippage_bps: int = 100) -> dict:
    ensure_dir()
    ticket = next_ticket_id()
    path = PROPOSALS_DIR / f"{ticket}.md"

    content = f"""# Proposal {ticket}

- **Ticket:** {ticket}
- **Mint:** `{mint}`
- **Size:** {size or "TBD"}
- **Max Slippage (bps):** {slippage_bps}
- **Status:** PENDING_RISK
- **Created:** {datetime.now(timezone.utc).isoformat()}

## RISK
(to be filled by RISK Bot)

## Context
(optional WHALE / SHILL notes)

## Human Approval
(required before SNIPER may act)

## Execution
(to be filled by SNIPER after fill)

## Exit / Journal
(to be filled by EXIT + CHIEF)
"""
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "ticket": ticket,
        "path": str(path),
        "mint": mint,
        "size": size,
        "slippage_bps": slippage_bps,
        "status": "PENDING_RISK",
    }


def main():
    parser = argparse.ArgumentParser(description="Ticket helper for PumpGrok")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("next", help="Print the next ticket ID (does not create a file)")

    create_p = sub.add_parser("create", help="Create a proposal skeleton file")
    create_p.add_argument("--mint", required=True, help="Token mint address")
    create_p.add_argument("--size", default=None, help="Intended size (e.g. 25 USDC or 0.1 SOL)")
    create_p.add_argument("--slippage", type=int, default=100, help="Max slippage in bps (default 100)")

    sub.add_parser("list", help="List existing proposal ticket IDs")

    args = parser.parse_args()

    if args.command == "next":
        result = {"ok": True, "ticket": next_ticket_id()}
        print(json.dumps(result, indent=2))
    elif args.command == "create":
        result = create_proposal(args.mint, args.size, args.slippage)
        print(json.dumps(result, indent=2))
    elif args.command == "list":
        ids = list_existing_ids()
        print(json.dumps({"ok": True, "tickets": ids, "count": len(ids)}, indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown command"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
