"""Operational paths shared by the CLI, the desk gateway and the reports.

Paths are relative to the working directory, as the CLI always resolved them.

- :data:`PAPER_LEDGER_PATH` is the one paper ledger (paper-engine.md 3.1). Every verb,
  the gateway and ``report --daily`` open this file. Replay writes its own per-dataset
  ledger under ``var/replay/<dataset>/`` (R21).
- :data:`DESK_DATA_DIR` is the desk operational directory. It holds the kill latch
  (``KILLSWITCH``, see ``pumpgrok.risk.killswitch.killswitch_file``), the journal, the
  reports and the bindings. The latch stays here, not beside the ledger.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["DESK_DATA_DIR", "PAPER_LEDGER_PATH"]

#: The canonical paper ledger, ``var/ledger.sqlite``.
PAPER_LEDGER_PATH = Path("var") / "ledger.sqlite"

#: The desk operational directory, ``var/desk``.
DESK_DATA_DIR = Path("var") / "desk"
