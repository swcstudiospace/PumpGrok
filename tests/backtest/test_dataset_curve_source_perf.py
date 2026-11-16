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
