"""Gap segmentation, 500 bps haircut flatten, cooldown entry ban."""

from __future__ import annotations

from pumpgrok.backtest.gaps import (
    GAP_HAIRCUT_BPS,
    entries_allowed,
    flatten_at_gaps,
    segment_dataset,
)


def test_segments_split_at_gaps() -> None:
    stamps = [0.0, 10.0, 20.0, 100.0, 110.0]
    segments = segment_dataset(stamps)
    assert len(segments) == 2
    assert (segments[0].start_ts, segments[0].end_ts, segments[0].size) == (0.0, 20.0, 3)
    assert (segments[1].start_ts, segments[1].end_ts, segments[1].size) == (100.0, 110.0, 2)


def test_no_gap_single_segment() -> None:
    assert len(segment_dataset([0.0, 5.0, 10.0])) == 1
    assert segment_dataset([]) == ()


def test_haircut_is_500_bps() -> None:
    assert GAP_HAIRCUT_BPS == 500
    assert flatten_at_gaps(100_000) == 95_000
    assert flatten_at_gaps(0) == 0


def test_no_entries_during_cooldown() -> None:
    gaps = [(100.0, 200.0)]
    assert entries_allowed(150.0, gaps) is False
    assert entries_allowed(230.0, gaps) is False  # 30s after gap end, inside cooldown
    assert entries_allowed(300.0, gaps) is True
    assert entries_allowed(50.0, gaps) is True
