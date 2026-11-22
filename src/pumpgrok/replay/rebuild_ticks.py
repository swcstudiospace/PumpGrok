"""Rebuild a ticks file from a sealed dataset (REC-03).

Deterministic: the same dataset always rebuilds the same tick bytes
(sorted keys, newline terminated), so reruns compare equal byte for byte.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.replay.fixtures import load_dataset

__all__ = ["rebuild_ticks"]


def rebuild_ticks(source_dir: Path, to_file: Path) -> Path:
    """Write the dataset's events as a deterministic ticks file; return its path."""
    dataset = load_dataset(Path(source_dir))
    lines = [json.dumps(event, sort_keys=True, separators=(",", ":")) for event in dataset.events]
    to_file = Path(to_file)
    to_file.parent.mkdir(parents=True, exist_ok=True)
    to_file.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    return to_file
