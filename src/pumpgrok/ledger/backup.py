"""Ledger backup and verified restore (HOST-07).

``backup_ledger`` writes a copy under the state directory.
``restore_ledger`` verifies the candidate hash chain before atomically
replacing the active file; a failed verification leaves the active file
byte-identical and is reported as failure.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def backup_ledger(active: str | Path, state_dir: str | Path, name: str = "ledger-backup.sqlite") -> Path:
    """Copy the active ledger under the state directory; returns the copy path."""
    src = Path(active)
    dest_dir = Path(state_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    shutil.copyfile(src, dest)
    return dest


def verify_candidate(candidate: str | Path) -> bool:
    """True iff the candidate's hash chain verifies."""
    from pumpgrok.ledger.store import LedgerStore  # noqa: PLC0415

    try:
        store = LedgerStore(candidate)
    except Exception:
        return False
    try:
        return bool(store.verify())
    except Exception:
        return False
    finally:
        try:
            store._db.close()
        except Exception:
            pass


def restore_ledger(candidate: str | Path, active: str | Path) -> bool:
    """Verify then atomically replace. False leaves the active file byte-identical."""
    cand = Path(candidate)
    act = Path(active)
    before = act.read_bytes() if act.exists() else None
    if not verify_candidate(cand):
        after = act.read_bytes() if act.exists() else None
        assert after == before
        return False
    act.parent.mkdir(parents=True, exist_ok=True)
    tmp = act.with_suffix(".tmp.sqlite")
    shutil.copyfile(cand, tmp)
    os.replace(tmp, act)
    return True
