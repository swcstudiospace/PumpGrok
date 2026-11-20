"""Live gate (R21): the nine preconditions, LiveGate and refusal_lines.

The refusing adapter lives in pumpgrok.execution.live.live_adapter and is imported
from that submodule only. This package does not re-export it (LIV-01).
"""

from pumpgrok.execution.live.live_gate import (
    PRECONDITION_IDS,
    LiveGate,
    Precondition,
    refusal_lines,
)

__all__ = [
    "PRECONDITION_IDS",
    "LiveGate",
    "Precondition",
    "refusal_lines",
]
