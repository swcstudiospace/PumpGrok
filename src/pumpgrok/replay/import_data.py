"""Import an external tick file into sealed form (REC-01).

Original timestamps are preserved verbatim; no timestamp is invented.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import WallClock
from pumpgrok.replay.fixtures import FixtureManifest
from pumpgrok.replay.live_recorder import LiveRecorder, seal_directory
from pumpgrok.replay.normalize import to_curve_tick


def import_ticks(
    source_path: Path, dataset_dir: Path, dataset_name: str, *, seed_hint: int = 0
) -> Path:
    """Convert an external JSONL tick file into a sealed dataset directory."""
    FixtureManifest._plain_dataset_name(dataset_name)
    recorder = LiveRecorder(Path(dataset_dir), clock=WallClock())
    first_utc: str | None = None
    last_utc: str | None = None
    sources: dict[str, str] = {}
    for line in Path(source_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise ValueError("external tick file has a blank line")
        record = json.loads(line)
        tick = to_curve_tick(record)
        recorder.record(
            CurveObservation(
                mint=tick.mint,
                ts_utc=tick.ts_utc,
                s_lamports=tick.virtual_sol_reserves_lamports,
                t_units=tick.virtual_token_reserves_units,
                complete=tick.complete,
                source=tick.curve_source,
            )
        )
        if first_utc is None:
            first_utc = tick.ts_utc
        last_utc = tick.ts_utc
        sources[tick.curve_source] = tick.curve_source
    if first_utc is None or last_utc is None:
        raise ValueError("cannot seal a dataset without observations")
    seal_directory(
        Path(dataset_dir),
        recorded_from_utc=first_utc,
        recorded_to_utc=last_utc,
        sources=sources,
        seed_hint=seed_hint,
        notes="Imported external tick file",
    )
    return Path(dataset_dir)
