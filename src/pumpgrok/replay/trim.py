"""Cut a sealed window without rewriting history (REC-01)."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.replay.clock import WallClock, parse_ts_utc
from pumpgrok.replay.fixtures import FixtureManifest, load_dataset
from pumpgrok.replay.live_recorder import LiveRecorder, seal_directory
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
    FixtureManifest._plain_dataset_name(dataset_name)
    dataset = load_dataset(Path(source_dir))
    start = parse_ts_utc(from_ts_utc)
    end = parse_ts_utc(to_ts_utc)
    recorder = LiveRecorder(Path(dest_dir), clock=WallClock())
    first_utc: str | None = None
    last_utc: str | None = None
    sources: dict[str, str] = {}
    for record in dataset.events:
        stamp = parse_ts_utc(str(record["ts_utc"]))
        if start <= stamp <= end:
            tick = to_curve_tick(dict(record))
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
        Path(dest_dir),
        recorded_from_utc=first_utc,
        recorded_to_utc=last_utc,
        sources=sources,
        seed_hint=seed_hint,
        notes=f"Trimmed window [{from_ts_utc}, {to_ts_utc}] from {Path(source_dir).name}",
    )
    return Path(dest_dir)
