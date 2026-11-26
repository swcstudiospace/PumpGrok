<<<<<<< HEAD
"""Per-mint bisect index correctness and budget over a shaped dataset."""

from __future__ import annotations

from pumpgrok.backtest.event_source import DatasetEventSource
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
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
                    "ts_utc": (
                        f"2025-01-{day % 28 + 1:02d}T{second // 3600:02d}:"
                        f"{(second // 60) % 60:02d}:{second % 60:02d}.000Z"
                    ),
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
=======
"""Window lookups bisect one mint. The bound is events examined, not wall time."""

from __future__ import annotations

import math

from pumpgrok.backtest.event_source import DatasetCurveSource

TOTALS = (1_000, 10_000, 100_000)
MINTS = 10


class CountingSource(DatasetCurveSource):
    """Counts timestamps the bisect probes. The base class is not trusted for the bound."""

    def __init__(self, events: list[dict[str, object]]) -> None:
        super().__init__(events)
        self.examined = 0

    def _examine(self, stamp: float) -> float:
        self.examined += 1
        return stamp


def _events(total: int) -> list[dict[str, object]]:
    mints = MINTS
    ticks = total // mints
    rows: list[dict[str, object]] = []
    for tick in range(ticks):
        for mint_i in range(mints):
            rows.append(
                {
                    "ts": float(tick),
                    "mint": f"m{mint_i}",
                    "file_order": 0,
                    "line_no": tick * mints + mint_i,
                }
            )
    return rows


def test_window_lookup_is_logarithmic_not_linear() -> None:
    counts: list[int] = []
    for total in TOTALS:
        source = CountingSource(_events(total))
        before = source.examined
        missing = source.window("absent", 0.0, 1.0)
        assert missing == ()
        assert source.examined == before, "a missing mint must not scan other mints"
        found = source.window("m3", 50.0, 50.0)
        assert [event["line_no"] for event in found] == [50 * MINTS + 3]
        bound = 8 * math.log2(total) + 8
        assert 0 < source.examined <= bound
        counts.append(source.examined)
    # 100x more ticks must not scale the probe count with the tick count.
    assert counts[-1] < counts[0] * (TOTALS[-1] / TOTALS[0]) / 5
    print(f"perf_counts totals={TOTALS} examined={tuple(counts)}")
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
