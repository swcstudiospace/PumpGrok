"""legacy_screening adapter: the legacy path through the runtime (STR-03).

The adapter is a thin wrapper over
:func:`pumpgrok.supervisor.scheduler.run_once_replay` with the same
dataset, filter config, seed, and ledger-path semantics as a direct call.
It holds no independent behavior and writes no attribution refs: a call
is a call, and parity with the direct path is proven in tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pumpgrok.supervisor.scheduler import run_once_replay

__all__ = ["run_legacy"]


def run_legacy(
    dataset_dir: str | Path,
    filter_cfg: Any,
    *,
    seed: int,
    ledger_path: str | Path,
) -> Any:
    """Replay the dataset through the legacy adapter (same as direct)."""
    return run_once_replay(dataset_dir, filter_cfg, seed=seed, ledger_path=ledger_path)
