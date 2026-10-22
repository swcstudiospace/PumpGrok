#!/usr/bin/env python3
"""Gates G-5 and G-6 — rollback plans and destructive operations.

G-5: no deployment without a rollback plan that names the command, the recovery time and the
     data implications. "We can roll back" is true of a deployment and frequently false of the
     system it deployed — a migration or a poisoned cache does not roll back with it.

G-6: destructive operations need explicit human approval recorded BEFORE execution, with the
     blast radius as understood at approval time.

    python3 ci/gates/check_rollback.py --receipt .receipts/deploy.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# (pattern, category, description). Categories: fs/git/data are kept from the precedent; ledger
# is a direct write to the event store; trade is live money or the halt and kill switch. The
# infrastructure rows (terraform, kubectl, helm, aws) are dropped: this repo has no such infra.
DESTRUCTIVE_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", "data", "drops a database object"),
    (r"\bTRUNCATE\b", "data", "empties a table"),
    (r"\bDELETE\s+FROM\b(?!.*\bWHERE\b)", "data", "unbounded delete"),
    (r"\bgit\s+push\b.*(?:--force|-f)\b", "git", "force push"),
    (r"\bgit\s+reset\s+--hard\b", "git", "discards work irrecoverably"),
    (r"\bgit\s+filter-(?:branch|repo)\b", "git", "rewrites history"),
    (r"\brm\s+(?:[^\n;&|]*\s)?(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)\b", "fs", "recursive delete"),
    (r"\bdocker\s+system\s+prune\b", "fs", "removes shared caches and volumes"),
    (r"\bdocker\s+volume\s+rm\b", "fs", "removes a volume"),
    (r"\bmkfs\b", "fs", "formats a filesystem"),
    (r"\bdd\s+.*of=/dev/", "fs", "writes directly to a device"),
    (r"\bexec\.place\b.*live", "trade", "places a live order"),
    (r"\bpumpgrok\s+live[-_ ]trade\b", "trade", "executes a live trade"),
    (r"\bpumpgrok\s+live\s+confirm\b", "trade", "writes a live human confirmation"),
    (r"\bwallet[-_ ]transfer\b", "trade", "moves funds out of a wallet"),
    (r"\bsend[-_ ]transaction\b", "trade", "sends an on-chain transaction"),
    (r"\bpumpgrok\s+risk\s+raise-limit\b", "trade", "raises a risk limit"),
    (r"\bpumpgrok\s+killswitch\s+clear\b", "trade", "clears the kill switch"),
    (r"\bpumpgrok\s+state\s+halt\b.*--clear\b", "trade", "clears a halt (R22: human only)"),
    (r"\brm\s+(?:-f\s+)?var/KILLSWITCH\b", "trade", "removes the kill switch file"),
    (r"\bDELETE\s+FROM\s+events\b", "ledger", "deletes ledger events"),
    (r"\bsqlite3\b.*var/ledger\.sqlite", "ledger", "writes to the ledger database directly"),
]

# A trade operation's approval must name the notional the human accepted (G-6).
TRADE_BLAST_RADIUS_RE = re.compile(r"^max_notional_sol=\d+(?:\.\d+)?$")

# Deployments put the desk on a live path (G-5). Paper runs are not deployments.
DEPLOY_PATTERNS = [
    r"\bpumpgrok\s+run\b.*--mode\s+live\b",
    r"\bpumpgrok\s+(?:go-live|promote)\b",
    r"\bPUMPGROK_LIVE_ENABLE=(?:1|true)\b",
    r"\bPUMPGROK_MODE=live\b",
    r"\bdocker\s+compose\s+up\b.*live",
    r"\bsystemctl\s+(?:start|restart|enable)\s+pumpgrok",
]

REQUIRED_APPROVAL_FIELDS = ["operation", "approved_by", "at", "blast_radius"]

# A rollback plan must say more than "roll back".
PLAN_MIN_WORDS = 12
PLAN_SIGNALS = [
    (
        r"(?i)\b(?:command|run|via|using|`|\bvercel\b|\bkubectl\b|\bterraform\b|\bgit\b|\bpumpgrok\b|\bkillswitch\b)",
        "the command or procedure",
    ),
    # NOTE: \bsecond\b does not match "seconds" — the trailing \b lands mid-word.
    (
        r"(?i)(?:seconds?|minutes?|hours?|instant|immediate|~\s*\d|\d+\s*(?:s|m|min|h)\b)",
        "the expected recovery time",
    ),
    (r"(?i)\b(?:data|schema|migration|cache|state|none|no data)\b", "the data implications"),
]


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"check_rollback: no receipt at {path}")
    return json.loads(path.read_text())


def find_matches(commands: list, patterns) -> list[tuple[int, str, str, str]]:
    hits = []
    for i, cmd in enumerate(commands):
        cmd_str = cmd.get("cmd", "") if isinstance(cmd, dict) else str(cmd)
        for entry in patterns:
            if isinstance(entry, tuple):
                pattern, category, desc = entry
            else:
                pattern, category, desc = entry, "deploy", "deployment"
            if re.search(pattern, cmd_str):
                hits.append((i, cmd_str, category, desc))
    return hits


def check_plan(plan: str | None) -> list[str]:
    if not plan or not str(plan).strip():
        return ["rollback_plan is empty"]

    problems = []
    text = str(plan)

    if len(text.split()) < PLAN_MIN_WORDS:
        problems.append(
            f"rollback_plan is {len(text.split())} words — too short to name a command, "
            f"a recovery time and the data implications"
        )

    for pattern, what in PLAN_SIGNALS:
        if not re.search(pattern, text):
            problems.append(f"rollback_plan does not state {what}")

    return problems


# An approval counts for a command only when its operation names that exact command. Two
# things are ignored: the pumpgrok CLI wrapper ("uv run pumpgrok ...") and trailing --by/--reason
# provenance flags, which the CLI records itself. Everything else must match, so a chained
# command ("a; b"), a prefix of the target ("rm -rf var/rep") or the bare verb ("rm -rf") never
# authorizes the full command.
CLI_WRAPPER_RE = re.compile(r"^(?:uv\s+run\s+)?(?:pumpgrok\s+)?")
# A provenance value is one shell word: a double-quoted or single-quoted string (which may hold
# spaces) or a bare non-space token. Quoted text cannot contain its own quote, so the suffix
# always ends at a closing quote and never swallows a following command.
PROVENANCE_VALUE = r"""(?:"[^"]*"|'[^']*'|\S+)"""
PROVENANCE_SUFFIX_RE = re.compile(rf"(?:\s+--(?:by|reason)\s+{PROVENANCE_VALUE})+$")


def operation_key(text: str) -> str:
    key = " ".join(str(text).split())
    key = CLI_WRAPPER_RE.sub("", key, count=1)
    return PROVENANCE_SUFFIX_RE.sub("", key, count=1)


def group_actions(hits: list) -> list[dict]:
    """One destructive action per command, however many patterns it matched."""
    actions: dict[int, dict] = {}
    for idx, cmd, category, desc in hits:
        action = actions.setdefault(
            idx, {"index": idx, "cmd": cmd, "categories": [], "descs": []}
        )
        if category not in action["categories"]:
            action["categories"].append(category)
        action["descs"].append(desc)
    return [actions[idx] for idx in sorted(actions)]


def approval_satisfies(approval, action: dict) -> bool:
    """A complete approval whose operation names this action (and, for trades, its notional)."""
    if not isinstance(approval, dict):
        return False
    if any(not approval.get(f) for f in REQUIRED_APPROVAL_FIELDS):
        return False
    key = operation_key(action["cmd"])
    if not key or operation_key(approval["operation"]) != key:
        return False
    if "trade" in action["categories"]:
        return bool(TRADE_BLAST_RADIUS_RE.match(str(approval["blast_radius"])))
    return True


def approval_problems(actions: list[dict], approvals: list) -> list[str]:
    """Each destructive action needs its own complete approval that names it (G-6)."""
    if not approvals:
        return [
            "destructive operations with NO approvals recorded.\n"
            "      These require explicit human approval BEFORE execution (G-6)."
        ]
    problems: list[str] = []
    for i, ap_rec in enumerate(approvals):
        if not isinstance(ap_rec, dict):
            problems.append(
                f"approvals[{i}] is not an object - an approval records what was "
                "approved, by whom, when, and the blast radius"
            )
            continue
        missing = [f for f in REQUIRED_APPROVAL_FIELDS if not ap_rec.get(f)]
        if missing:
            problems.append(
                f"approvals[{i}] is missing {missing} — an approval records what was "
                "approved, by whom, when, and the blast radius"
            )
    # Greedy assignment is exact here: commands with equal text have equal categories, and an
    # approval names exactly one command text, so eligibility sets never overlap across actions.
    used: set[int] = set()
    for action in actions:
        idx = next(
            (
                i
                for i, ap in enumerate(approvals)
                if i not in used and approval_satisfies(ap, action)
            ),
            None,
        )
        if idx is None:
            trade = "trade" in action["categories"]
            cats = "/".join(action["categories"])
            note = (
                " and whose blast_radius is 'max_notional_sol=<float>' - the notional "
                "the human approved (G-6)"
                if trade
                else " (G-6)"
            )
            problems.append(
                f"[{action['index']}] ({cats}) {action['cmd']}: no approval whose "
                f"operation names this command{note}"
            )
        else:
            used.add(idx)
    return problems


def check_destructive(commands: list, approvals: list) -> tuple[list[dict], list[str]]:
    """G-6: group matches into actions and verify each action has its own approval."""
    actions = group_actions(find_matches(commands, DESTRUCTIVE_PATTERNS))
    if actions:
        print(f"G-6 — {len(actions)} destructive operation(s) detected:")
        for action in actions:
            cats = "/".join(action["categories"])
            print(f"    [{action['index']}] ({cats}) {action['cmd']}")
            for desc in dict.fromkeys(action["descs"]):
                print(f"         {desc}")
    problems = approval_problems(actions, approvals) if actions else []
    return actions, problems


def check_deployments(commands: list, receipt: dict) -> tuple[list, list[str]]:
    """G-5: deployments need a rollback plan covering command, time, and data."""
    deploys = find_matches(commands, DEPLOY_PATTERNS)
    if deploys:
        print(f"G-5 — {len(deploys)} deployment command(s) detected:")
        for idx, cmd, _cat, _desc in deploys:
            print(f"    [{idx}] {cmd}")
    plans = check_plan(receipt.get("rollback_plan")) if deploys else []
    return deploys, [f"G-5: {p}" for p in plans]


def main() -> int:
    ap = argparse.ArgumentParser(description="Gates G-5/G-6: rollback and destructive ops")
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()

    receipt = load(args.receipt)
    commands = receipt.get("commands", [])
    approvals = receipt.get("approvals", []) or []
    # --- G-6: destructive operations --------------------------------------
    destructive, problems = check_destructive(commands, approvals)

    # --- G-5: deployments need a rollback plan ----------------------------
    deploys, deploy_problems = check_deployments(commands, receipt)
    problems.extend(deploy_problems)

    if problems:
        print("\nG-5/G-6 FAIL", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("\n  See docs/quality-gates.md G-5 and G-6", file=sys.stderr)
        return 1

    if not destructive and not deploys:
        print("G-5/G-6 PASS — no deployments or destructive operations in this receipt")
    else:
        print(
            f"\nG-5/G-6 PASS — {len(deploys)} deployment(s) with a rollback plan, "
            f"{len(destructive)} destructive op(s) approved"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
