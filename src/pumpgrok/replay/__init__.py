"""Deterministic replay primitives: clock, seeded RNG, manifest-gated fixtures.

`clock` is imported first: `pumpgrok.core.ids` re-exports `Clock` from it, and
`fixtures` depends on `pumpgrok.core.errors`.
"""

from pumpgrok.replay.clock import (
    Clock,
    FixtureClock,
    WallClock,
    format_ts_utc,
    parse_ts_utc,
)
from pumpgrok.replay.fixtures import (
    CorruptFixture,
    FixtureDataset,
    FixtureManifest,
    event_epoch,
    load_dataset,
    read_jsonl,
    verify_manifest,
)
from pumpgrok.replay.rng import DEFAULT_SEED, make_rng

__all__ = [
    "DEFAULT_SEED",
    "Clock",
    "CorruptFixture",
    "FixtureClock",
    "FixtureDataset",
    "FixtureManifest",
    "WallClock",
    "event_epoch",
    "format_ts_utc",
    "load_dataset",
    "make_rng",
    "parse_ts_utc",
    "read_jsonl",
    "verify_manifest",
]
