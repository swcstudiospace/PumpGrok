"""Import an external tick file into sealed form (REC-01).

Original timestamps are preserved verbatim; no timestamp is invented.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.replay.live_recorder import LiveRecorder, validate_dataset_name
from pumpgrok.replay.normalize import to_curve_tick


def import_ticks(
    source_path: Path, dataset_dir: Path, dataset_name: str, *, seed_hint: int = 0
) -> Path:
    """Convert an external JSONL tick file into a sealed dataset directory."""
    validate_dataset_name(dataset_name)
    recorder = LiveRecorder(Path(dataset_dir))
    for line in Path(source_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise ValueError("external tick file has a blank line")
        record = json.loads(line)
        recorder.record_tick(to_curve_tick(record))
    return recorder.seal(dataset_name, seed_hint=seed_hint)
