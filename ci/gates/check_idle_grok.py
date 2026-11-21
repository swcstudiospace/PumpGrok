#!/usr/bin/env python3
"""Idle-Grok CI gate (EVT-12).

Replays 24 virtual hours of silence through the bus and counts Grok gateway
calls. Prints the call count only. Exit 0 on zero calls, non-zero
otherwise. Virtual time only: the gate cannot hang on wall-clock time.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pumpgrok.events.idle import run_idle_grok_calls  # noqa: E402


def main() -> int:
    calls = run_idle_grok_calls()
    print(f"idle-grok calls={calls}")
    return 0 if calls == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
