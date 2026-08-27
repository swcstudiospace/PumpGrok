#!/usr/bin/env python3
"""
ticket_helper.py – Generate next PumpGrok ticket ID and optional proposal skeleton.

Usage:
  python tools/ticket_helper.py next
  python tools/ticket_helper.py create --mint <mint> [--ticket SOL-YYYYMMDD-NNN]
           [--size <usd_or_sol>] [--slippage 100] [--status PENDING_HUMAN]
  python tools/ticket_helper.py list

Desk root resolution:
  PUMPGROK_DESK, then /workspace/trading-desk, then ./trading-desk

Ticket IDs are unique across leads/, briefs/, proposals/, positions/,
incidents/, watch/, research/, and journal/. Never signs or sends.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


TICKET_RE = re.compile(r"SOL-\d{8}-\d{3}")
SCAN_CHILDREN = (
    "proposals",
    "briefs",
    "leads",
    "research",
    "journal",
    "incidents",
    "positions",
    "watch",
)


def desk_root() -> Path:
    env = os.environ.get("PUMPGROK_DESK")
    if env:
        return Path(env).expanduser().resolve()
    workspace = Path("/workspace/trading-desk")
    if workspace.exists() or Path("/workspace").exists():
        return workspace
    return (Path.cwd() / "trading-desk").resolve()


def proposals_dir() -> Path:
    return desk_root() / "proposals"


def ensure_dir() -> Path:
    path = proposals_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def list_existing_ids() -> List[str]:
    desk = desk_root()
    found = set()
    for child in SCAN_CHILDREN:
        folder = desk / child
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                match = TICKET_RE.search(path.name)
                if match:
                    found.add(match.group(0))
    return sorted(found)


def next_ticket_id() -> str:
    today = today_str()
    prefix = f"SOL-{today}-"
    seq = 1
    for ticket in list_existing_ids():
        if ticket.startswith(prefix):
            seq = max(seq, int(ticket.split("-")[-1]) + 1)
    return f"{prefix}{seq:03d}"


def create_proposal(
    mint: str,
    size: Optional[str] = None,
    slippage_bps: int = 100,
    ticket: Optional[str] = None,
    status: str = "PENDING_RISK",
) -> dict:
    folder = ensure_dir()
    if ticket:
        if not TICKET_RE.fullmatch(ticket):
            return {"ok": False, "error": f"invalid ticket id: {ticket}"}
    else:
        ticket = next_ticket_id()
    path = folder / f"{ticket}.md"
    if path.exists():
        return {
            "ok": False,
            "error": "proposal already exists",
            "ticket": ticket,
            "path": str(path),
            "desk": str(desk_root()),
        }

    content = f"""# Proposal {ticket}

- **Ticket:** {ticket}
- **Mint:** `{mint}`
- **Size:** {size or "TBD"}
- **Max Slippage (bps):** {slippage_bps}
- **Status:** {status}
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
        "status": status,
        "desk": str(desk_root()),
    }


def main():
    parser = argparse.ArgumentParser(description="Ticket helper for PumpGrok")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("next", help="Print the next ticket ID (does not create a file)")

    create_p = sub.add_parser("create", help="Create a proposal skeleton file")
    create_p.add_argument("--mint", required=True, help="Token mint address")
    create_p.add_argument("--ticket", default=None, help="Reuse an existing LEAD-ID")
    create_p.add_argument("--size", default=None, help="Intended size (e.g. 25 USDC or 0.1 SOL)")
    create_p.add_argument("--slippage", type=int, default=100, help="Max slippage in bps (default 100)")
    create_p.add_argument("--status", default="PENDING_RISK", help="Proposal status field")

    sub.add_parser("list", help="List existing ticket IDs across the desk")

    args = parser.parse_args()

    if args.command == "next":
        result = {"ok": True, "ticket": next_ticket_id(), "desk": str(desk_root())}
        print(json.dumps(result, indent=2))
    elif args.command == "create":
        result = create_proposal(
            args.mint,
            args.size,
            args.slippage,
            ticket=args.ticket,
            status=args.status,
        )
        print(json.dumps(result, indent=2))
        if not result.get("ok"):
            sys.exit(1)
    elif args.command == "list":
        ids = list_existing_ids()
        print(json.dumps({"ok": True, "tickets": ids, "count": len(ids), "desk": str(desk_root())}, indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown command"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
