"""Atomic desk.md mirrors for halt and kill-switch rows (paper-engine.md 3.6, R26).

Same visible contract as ``tools/desk_state.py`` (``Halt: true`` plus the
``FLOOR HALTED`` line the Hermes cron gate scans for), but every write goes
through tmp-file plus fsync plus ``os.replace`` instead of an in-place write.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HALT_RE = re.compile(r"(?im)^\s*[-*]?\s*\**Halt:\**\s*(true|false|yes|no|1|0)")


def _atomic_write_text(path: Path, body: str) -> None:
    """Write text atomically: tmp file in the same dir, fsync, os.replace."""
    tmp = path.parent / f"{path.name}.tmp{os.getpid()}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _with_halt_flag(body: str, active: bool) -> str:
    value = "true" if active else "false"
    if not HALT_RE.search(body):
        return body + f"\nHalt: {value}\n"
    return HALT_RE.sub(f"Halt: {value}", body, count=1)


def mirror_halt(desk_dir: str | Path, *, reason: str, ts_utc: str) -> Path:
    """Mirror a HaltSet row into desk.md; returns the mirror path."""
    path = Path(desk_dir) / "desk.md"
    body = path.read_text(encoding="utf-8") if path.exists() else "# Desk\n"
    body = _with_halt_flag(body, True)
    body += f"\nFLOOR HALTED - {reason} @ {ts_utc}\n"
    _atomic_write_text(path, body)
    return path


def mirror_halt_cleared(desk_dir: str | Path, *, reason: str, cleared_by: str, ts_utc: str) -> Path:
    """Mirror a HaltCleared row into desk.md; returns the mirror path."""
    path = Path(desk_dir) / "desk.md"
    body = path.read_text(encoding="utf-8") if path.exists() else "# Desk\n"
    body = _with_halt_flag(body, False)
    body += f"\nHALT CLEARED - {reason} by {cleared_by} @ {ts_utc}\n"
    _atomic_write_text(path, body)
    return path


def mirror_killswitch(desk_dir: str | Path, *, source: str, reason: str, ts_utc: str) -> Path:
    """Mirror a KillSwitchSet row into desk.md; returns the mirror path."""
    path = Path(desk_dir) / "desk.md"
    body = path.read_text(encoding="utf-8") if path.exists() else "# Desk\n"
    body = _with_halt_flag(body, True)
    body += f"\nFLOOR HALTED - KILL SWITCH ({source}): {reason} @ {ts_utc}\n"
    _atomic_write_text(path, body)
    return path
