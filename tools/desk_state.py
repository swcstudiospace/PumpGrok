#!/usr/bin/env python3
"""
desk_state.py – File-bus status for the PumpGrok cron state machine.

No network. No signing. JSON on stdout.
Resolves the desk from PUMPGROK_DESK, then /workspace/trading-desk, then ./trading-desk.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


DESK_CHILDREN = (
    "proposals",
    "briefs",
    "leads",
    "research",
    "journal",
    "incidents",
    "positions",
    "watch",
)

TICKET_RE = re.compile(r"SOL-\d{8}-\d{3}")
VERDICT_RE = re.compile(r"(?im)^Verdict:\s*(CLEAR|CONDITIONAL|KILL|BLIND)\s*$")
STATUS_RE = re.compile(r"(?im)^\s*[-*]?\s*\**Status:\**\s*([A-Z0-9_]+)")
ENGAGEMENT_RE = re.compile(r"(?im)^\s*[-*]?\s*\**Engagement:\**\s*([a-z-]+)")
HALT_RE = re.compile(r"(?im)^\s*[-*]?\s*\**Halt:\**\s*(true|false|yes|no|1|0)")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    env = os.environ.get("PUMPGROK_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def desk_root() -> Path:
    env = os.environ.get("PUMPGROK_DESK")
    if env:
        return Path(env).expanduser().resolve()
    workspace = Path("/workspace/trading-desk")
    if workspace.exists() or Path("/workspace").exists():
        return workspace
    return (Path.cwd() / "trading-desk").resolve()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def parse_desk_md(text: str) -> Dict[str, object]:
    engagement = "research"
    halt = False
    m = ENGAGEMENT_RE.search(text)
    if m:
        engagement = m.group(1).strip().lower()
    h = HALT_RE.search(text)
    if h:
        halt = h.group(1).strip().lower() in {"true", "yes", "1"}
    if re.search(r"FLOOR HALTED", text, re.I):
        halt = True
    return {"engagement": engagement, "halt": halt}


def ticket_id_from_name(path: Path) -> Optional[str]:
    m = TICKET_RE.search(path.stem)
    return m.group(0) if m else None


def list_ticket_files(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and TICKET_RE.search(p.stem)]
    return sorted(files)


def all_ticket_ids(desk: Path) -> List[str]:
    found = set()
    for child in DESK_CHILDREN:
        folder = desk / child
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                match = TICKET_RE.search(path.name)
                if match:
                    found.add(match.group(0))
    return sorted(found)


def next_ticket_id(desk: Path) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"SOL-{today}-"
    seq = 1
    for tid in all_ticket_ids(desk):
        if tid.startswith(prefix):
            seq = max(seq, int(tid.split("-")[-1]) + 1)
    return f"{prefix}{seq:03d}"


def pending_leads(desk: Path) -> List[Dict[str, str]]:
    leads = list_ticket_files(desk / "leads")
    briefs = {ticket_id_from_name(p) for p in list_ticket_files(desk / "briefs")}
    out = []
    for lead in leads:
        tid = ticket_id_from_name(lead)
        if tid and tid not in briefs:
            out.append({"ticket": tid, "path": str(lead)})
    return out


def brief_verdict(path: Path) -> Optional[str]:
    m = VERDICT_RE.search(read_text(path))
    return m.group(1).upper() if m else None


def proposal_status(path: Path) -> Optional[str]:
    m = STATUS_RE.search(read_text(path))
    return m.group(1).upper() if m else None


def pending_tickets(desk: Path) -> List[Dict[str, str]]:
    out = []
    for brief in list_ticket_files(desk / "briefs"):
        tid = ticket_id_from_name(brief)
        if not tid:
            continue
        verdict = brief_verdict(brief) or "UNKNOWN"
        proposal = desk / "proposals" / f"{tid}.md"
        item = {
            "ticket": tid,
            "brief": str(brief),
            "verdict": verdict,
            "proposal": str(proposal) if proposal.exists() else "",
            "proposal_status": proposal_status(proposal) if proposal.exists() else "",
        }
        out.append(item)
    return out


def open_positions(desk: Path) -> List[Dict[str, str]]:
    folder = desk / "positions"
    if not folder.exists():
        return []
    out = []
    for path in sorted(p for p in folder.iterdir() if p.is_file()):
        text = read_text(path)
        if re.search(r"(?im)status:\s*(closed|exited|killed)", text):
            continue
        out.append({"path": str(path), "ticket": ticket_id_from_name(path) or ""})
    return out


def ensure_desk(desk: Path) -> None:
    for name in DESK_CHILDREN:
        (desk / name).mkdir(parents=True, exist_ok=True)
    desk_md = desk / "desk.md"
    if not desk_md.exists():
        desk_md.write_text(
            (
                "# PumpGrok Desk Record\n"
                f"Date: {utc_now()}\n"
                "Engagement: research\n"
                "Halt: false\n"
                "Throwaway wallet: not yet connected\n"
                "Daily loss limit: 5 %\n"
                "Notes: Cron state machine installed. Research only.\n"
            ),
            encoding="utf-8",
        )
    limits = desk / "risk-limits.md"
    if not limits.exists():
        limits.write_text(
            "# Risk limits\n\nStatus: interview pending\nDefault paper size: TBD\n",
            encoding="utf-8",
        )


def write_halt(desk: Path, reason: str) -> Dict[str, object]:
    ensure_desk(desk)
    path = desk / "desk.md"
    body = read_text(path)
    if not HALT_RE.search(body):
        body += "\nHalt: true\n"
    else:
        body = HALT_RE.sub("Halt: true", body, count=1)
    stamp = utc_now()
    body += f"\nFLOOR HALTED – {reason} @ {stamp}\n"
    path.write_text(body, encoding="utf-8")
    journal = desk / "journal" / f"{stamp[:10]}.md"
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} HALT {reason}\n")
    return {"ok": True, "halt": True, "reason": reason, "path": str(path)}


def status_payload(desk: Path) -> Dict[str, object]:
    ensure_desk(desk)
    parsed = parse_desk_md(read_text(desk / "desk.md"))
    return {
        "ok": True,
        "utc": utc_now(),
        "repo": str(repo_root()),
        "desk": str(desk),
        "engagement": parsed["engagement"],
        "halt": parsed["halt"],
        "pending_leads": pending_leads(desk),
        "pending_tickets": pending_tickets(desk),
        "open_positions": open_positions(desk),
        "known_tickets": all_ticket_ids(desk),
        "next_ticket": next_ticket_id(desk),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="PumpGrok desk file-bus status")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("pending-leads")
    sub.add_parser("pending-tickets")
    sub.add_parser("open-positions")
    sub.add_parser("ensure")
    sub.add_parser("next-id")
    halt_p = sub.add_parser("halt")
    halt_p.add_argument("--reason", required=True)
    args = parser.parse_args()

    desk = desk_root()
    if args.command == "ensure":
        ensure_desk(desk)
        print(json.dumps({"ok": True, "desk": str(desk)}, indent=2))
        return 0
    if args.command == "status":
        print(json.dumps(status_payload(desk), indent=2))
        return 0
    if args.command == "pending-leads":
        print(json.dumps({"ok": True, "items": pending_leads(desk)}, indent=2))
        return 0
    if args.command == "pending-tickets":
        print(json.dumps({"ok": True, "items": pending_tickets(desk)}, indent=2))
        return 0
    if args.command == "open-positions":
        print(json.dumps({"ok": True, "items": open_positions(desk)}, indent=2))
        return 0
    if args.command == "next-id":
        ensure_desk(desk)
        print(json.dumps({"ok": True, "ticket": next_ticket_id(desk), "desk": str(desk)}, indent=2))
        return 0
    if args.command == "halt":
        print(json.dumps(write_halt(desk, args.reason), indent=2))
        return 0
    print(json.dumps({"ok": False, "error": "unknown command"}))
    return 1


if __name__ == "__main__":
    sys.exit(main())
