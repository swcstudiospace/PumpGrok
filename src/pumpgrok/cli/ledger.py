"""`pumpgrok ledger backup|restore` (HOST-07)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pumpgrok.cli.errors import _say
from pumpgrok.config.settings import Settings, state_root
from pumpgrok.ledger.backup import backup_ledger, restore_ledger


def _ledger_verb(args: argparse.Namespace, settings: Settings) -> int:
    cmd = getattr(args, "cmd", None)
    active = Path(getattr(args, "ledger", "var/ledger.sqlite"))
    root = state_root() or Path("var")
    if cmd == "backup":
        dest = backup_ledger(active, root)
        _say(sys.stdout, f"backup written: {dest}")
        return 0
    if cmd == "restore":
        candidate = Path(getattr(args, "from_", ""))
        if not candidate.is_file():
            _say(sys.stderr, "restore refused: candidate missing")
            return 1
        if not restore_ledger(candidate, active):
            _say(sys.stderr, "restore refused: hash chain verification failed")
            return 1
        _say(sys.stdout, f"restored: {active}")
        return 0
    _say(sys.stderr, "ledger: expected backup or restore")
    return 1


__all__ = ["_ledger_verb"]
