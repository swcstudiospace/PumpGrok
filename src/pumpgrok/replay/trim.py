"""Cut a sealed window without rewriting history (REC-01)."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.replay.clock import WallClock, parse_ts_utc
from pumpgrok.replay.fixtures import load_dataset
from pumpgrok.replay.live_recorder import LiveRecorder, validate_dataset_name
from pumpgrok.replay.normalize import to_curve_tick


def trim_dataset(
    source_dir: Path,
    dest_dir: Path,
    dataset_name: str,
    *,
    from_ts_utc: str,
    to_ts_utc: str,
    seed_hint: int = 0,
) -> Path:
    """Copy the inclusive sealed window [from_ts_utc, to_ts_utc] into a new dataset.

    The source is verified first via ``load_dataset`` and never mutated.
    """
    validate_dataset_name(dataset_name)
    dataset = load_dataset(Path(source_dir))
    start = parse_ts_utc(from_ts_utc)
    end = parse_ts_utc(to_ts_utc)
    recorder = LiveRecorder(Path(dest_dir), clock=WallClock(), dataset_name=dataset_name)
    for record in dataset.events:
        stamp = parse_ts_utc(str(record["ts_utc"]))
        if start <= stamp <= end:
            recorder.record_tick(to_curve_tick(dict(record)))
    return recorder.seal_dataset(dataset_name, seed_hint=seed_hint)
