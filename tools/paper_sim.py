#!/usr/bin/env python3
"""
paper_sim.py – Simple paper-trading fill logger for PumpGrok.

Usage (buy):
  python tools/paper_sim.py --action buy --ticket SOL-20260827-001 \
      --mint <mint> --size-usd 50 --price 0.0000123 --slippage-bps 80

Usage (sell):
  python tools/paper_sim.py --action sell --ticket SOL-20260827-001 \
      --mint <mint> --size-usd 50 --price 0.0000150 --reason TP

Appends a structured paper fill to the journal. Never touches real capital.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def append_paper_fill(desk: Path, record: Dict[str, Any]) -> str:
    journal_dir = desk / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = journal_dir / f"paper-{day}.md"

    line = (
        f"\n### PAPER {record['action'].upper()} | {record['ticketId']}\n"
        f"- UTC: {record['utc']}\n"
        f"- Mint: {record['mint']}\n"
        f"- Size USD: {record['sizeUsd']}\n"
        f"- Price: {record['price']}\n"
        f"- Slippage bps: {record.get('slippageBps', 'n/a')}\n"
        f"- Reason: {record.get('reason', '')}\n"
        f"- Note: {record.get('note', '')}\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
    return str(path)


def main():
    parser = argparse.ArgumentParser(description="Paper fill logger for PumpGrok")
    parser.add_argument("--desk", default="/workspace/trading-desk")
    parser.add_argument("--action", choices=["buy", "sell"], required=True)
    parser.add_argument("--ticket", required=True, help="Ticket ID e.g. SOL-20260827-001")
    parser.add_argument("--mint", required=True)
    parser.add_argument("--size-usd", type=float, required=True)
    parser.add_argument("--price", type=float, required=True)
    parser.add_argument("--slippage-bps", type=int, default=0)
    parser.add_argument("--reason", default="")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    record = {
        "ok": True,
        "mode": "paper",
        "action": args.action,
        "ticketId": args.ticket,
        "mint": args.mint,
        "sizeUsd": args.size_usd,
        "price": args.price,
        "slippageBps": args.slippage_bps,
        "reason": args.reason,
        "note": args.note,
        "utc": datetime.now(timezone.utc).isoformat(),
    }

    try:
        path = append_paper_fill(Path(args.desk), record)
        record["journalPath"] = path
    except Exception as e:
        record["ok"] = False
        record["error"] = str(e)

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
