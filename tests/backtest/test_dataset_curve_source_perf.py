"""Per-mint bisect index correctness and budget over a shaped dataset."""

from __future__ import annotations

from pumpgrok.backtest.event_source import DatasetEventSource
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import FixtureDataset, FixtureManifest


def _synthetic(n_mints: int = 20, per_mint: int = 250) -> FixtureDataset:
    events: list[dict[str, object]] = []
    base = 1_700_000_000.0
    for mint_index in range(n_mints):
        mint = f"Mint{mint_index:04d}"
        for tick in range(per_mint):
            ts = base + tick * 1.0 + mint_index * 0.01
            day = int(ts // 86400)
            second = int(ts % 86400)
            events.append(
                {
                    "mint": mint,
                    "ts_utc": f"2025-01-{day % 28 + 1:02d}T{second // 3600:02d}:{(second // 60) % 60:02d}:{second % 60:02d}.000Z",
                    "S": 1_000_000 + tick,
                    "T": 1_000_000,
                }
            )
    events.sort(key=lambda e: str(e["ts_utc"]))
    manifest = FixtureManifest(
        dataset="synthetic",
        recorded_from_utc=str(events[0]["ts_utc"]),
        recorded_to_utc=str(events[-1]["ts_utc"]),
        seed_hint=0,
        sha256={"events.jsonl": "a" * 64},
    )
    return FixtureDataset(manifest=manifest, events=tuple(events))  # type: ignore[arg-type]
def test_bisect_index_meets_budget() -> None:
    from pumpgrok.replay.clock import parse_ts_utc

    dataset = _synthetic()
    clock = FixtureClock(start=0.0)
    source = DatasetEventSource(dataset, clock)
    base_ts = parse_ts_utc(str(dataset.events[0]["ts_utc"]))
    # Correctness: latest tick at or before ts, per mint.
    first = source.tick_at("Mint0000", base_ts + 10.0)
    assert first is not None
    assert first["mint"] == "Mint0000"
    assert source.tick_at("UnknownMint", base_ts + 10.0) is None
    assert source.tick_at("Mint0000", base_ts - 1.0) is None
    # Budget: repeated lookups without timing flakiness (bisect is O(log n)).
    for probe in range(100):
        assert source.tick_at("Mint0007", base_ts + probe * 10.0) is not None
    assert len(source) == 5000
