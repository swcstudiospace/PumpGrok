#!/usr/bin/env python3
"""Run every gate. The single entry point for CI and for local pre-flight.

    python3 ci/gates/run_all.py --bot bot-04-sniper --base origin/main \
        --receipt .receipts/bot-04-sniper/feat-paper-fill.json
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

GATES_DIR = Path(__file__).resolve().parent
REPO_ROOT = GATES_DIR.parents[1]


def run(name: str, argv: list[str]) -> tuple[str, int]:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    result = subprocess.run([sys.executable, "-P", *argv], cwd=REPO_ROOT, check=False)
    return name, result.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Run all quality gates")
    ap.add_argument("--bot", required=True)
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--change", type=Path, help="Contract change document, if any")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    results: list[tuple[str, int]] = []

    results.append(
        run(
            "G-1  Path ownership",
            [str(GATES_DIR / "check_ownership.py"), "--bot", args.bot, "--base", args.base],
        )
    )

    receipt_argv = [
        str(GATES_DIR / "check_receipt.py"),
        "--receipt",
        str(args.receipt),
        "--bot",
        args.bot,
    ]
    if args.strict:
        receipt_argv.append("--strict")
    results.append(run("G-2  Verification receipt", receipt_argv))

    results.append(
        run(
            "G-3  Committed secrets",
            [str(GATES_DIR / "check_secrets.py"), "--base", args.base],
        )
    )

    contracts_argv = [str(GATES_DIR / "check_contracts.py"), "--base", args.base]
    if args.change:
        contracts_argv += ["--change", str(args.change)]
    results.append(run("G-4  Contract-first changes", contracts_argv))

    results.append(
        run(
            "G-5/G-6  Rollback and destructive ops",
            [str(GATES_DIR / "check_rollback.py"), "--receipt", str(args.receipt)],
        )
    )

    # G-7 reads the repo as it is rather than a diff or a receipt, so it takes no --bot and
    # always runs: a bad roster is bad on every commit, not only the one that introduced it.
    results.append(
        run(
            "G-7  Desk integrity",
            [str(GATES_DIR / "check_desk_integrity.py"), "--repo", str(REPO_ROOT)],
        )
    )

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    failed = 0
    for name, code in results:
        status = "PASS" if code == 0 else "FAIL"
        if code != 0:
            failed += 1
        print(f"  [{status}]  {name}")

    if failed:
        print(f"\n{failed} gate(s) failed. Fix the cause — never bypass a gate (PD-3).")
        return 1

    print("\nAll gates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
