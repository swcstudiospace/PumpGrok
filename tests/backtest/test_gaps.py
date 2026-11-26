<<<<<<< HEAD
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
=======
"""Gap flatten, exclusion, cooldown and torn gaps.jsonl (BT-11)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.backtest.gaps import segment
from pumpgrok.backtest.grading import APPROVED_THRESHOLDS
from pumpgrok.replay.clock import format_ts_utc

_BPS = 10_000
_MINT = "MintGap"
_DEPOSIT = 2_039_280
_MARK = 80_000
_COST = _MARK + _DEPOSIT


def test_open_position_is_flattened_at_last_mark_less_haircut(tmp_path: Path) -> None:
    gap_start, _gap_end = _gap_file(tmp_path, start=50.0, end=80.0)
    _events(
        tmp_path,
        [
            _open(10.0, _MARK),
            _mark(20.0, _MARK),
            _tick(49.0),
            _tick(51.0),
        ],
    )
    result = segment(
        tmp_path,
        tmp_path / "gaps.jsonl",
        APPROVED_THRESHOLDS.cooldown_s,
        APPROVED_THRESHOLDS.haircut_bps,
    )
    assert len(result.flags) == 1
    flag = result.flags[0]
    assert flag.action == "flatten"
    assert flag.mint == _MINT
    assert flag.gap_start == gap_start
    assert flag.last_mark_lamports == _MARK
    assert flag.flatten_lamports == _MARK * (_BPS - APPROVED_THRESHOLDS.haircut_bps) // _BPS
    assert flag.refund_lamports == _DEPOSIT
    assert flag.realized_lamports == flag.flatten_lamports - (_COST - _DEPOSIT)
    assert flag.realized_lamports != flag.flatten_lamports + _DEPOSIT - (_COST - _DEPOSIT)
    assert _MINT not in result.open_mints


def test_exclusion_removes_and_flags_the_open_position(tmp_path: Path) -> None:
    _gap_file(tmp_path, start=50.0, end=80.0)
    _events(tmp_path, [_open(10.0, _MARK), _tick(90.0)])
    result = segment(
        tmp_path,
        tmp_path / "gaps.jsonl",
        APPROVED_THRESHOLDS.cooldown_s,
        APPROVED_THRESHOLDS.haircut_bps,
        exclude=True,
    )
    assert len(result.flags) == 1
    flag = result.flags[0]
    assert flag.action == "exclude"
    assert flag.flatten_lamports is None
    assert flag.refund_lamports == _DEPOSIT
    assert _MINT not in result.open_mints


def test_no_entry_during_cooldown_and_first_after_is_allowed(tmp_path: Path) -> None:
    step = float(APPROVED_THRESHOLDS.max_single_gap_s)
    gap_start = step
    gap_end = step + 1.0
    _gap_file(tmp_path, start=gap_start, end=gap_end)
    last = gap_end + APPROVED_THRESHOLDS.cooldown_s + step
    stamps = []
    cursor = 0.0
    while cursor < last:
        stamps.append(cursor)
        cursor += step
    stamps.append(last)
    _events(tmp_path, [_tick(stamp) for stamp in stamps])
    result = segment(
        tmp_path,
        tmp_path / "gaps.jsonl",
        APPROVED_THRESHOLDS.cooldown_s,
        APPROVED_THRESHOLDS.haircut_bps,
    )
    cooldown_end = gap_end + APPROVED_THRESHOLDS.cooldown_s
    assert result.entry_allowed(gap_end) is False
    assert result.entry_allowed(cooldown_end - 1) is False
    assert result.entry_allowed(cooldown_end) is True
    assert all(segment_row.allows_entry(gap_end) is False for segment_row in result.segments)


def test_torn_gaps_jsonl_tail_is_tolerated(tmp_path: Path) -> None:
    start = format_ts_utc(10.0)
    end = format_ts_utc(40.0)
    intact = json.dumps(
        {"end_ts_utc": end, "reason": "feed", "start_ts_utc": start},
        sort_keys=True,
    )
    (tmp_path / "gaps.jsonl").write_bytes((intact + "\n" + '{"start_ts_utc":').encode("utf-8"))
    _events(tmp_path, [_tick(0.0), _tick(80.0)])
    result = segment(
        tmp_path,
        tmp_path / "gaps.jsonl",
        APPROVED_THRESHOLDS.cooldown_s,
        APPROVED_THRESHOLDS.haircut_bps,
    )
    assert result.torn_tail_dropped is True
    assert len(result.gap_intervals) == 1
    assert result.gap_intervals[0][0] == 10.0


def _gap_file(directory: Path, *, start: float, end: float) -> tuple[float, float]:
    line = {
        "end_ts_utc": format_ts_utc(end),
        "reason": "feed",
        "start_ts_utc": format_ts_utc(start),
    }
    (directory / "gaps.jsonl").write_text(json.dumps(line, sort_keys=True) + "\n", encoding="utf-8")
    return start, end


def _events(directory: Path, events: list[dict[str, object]]) -> None:
    text = "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n"
    (directory / "events.jsonl").write_text(text, encoding="utf-8")


def _open(ts: float, mark: int) -> dict[str, object]:
    return {
        "kind": "open",
        "mint": _MINT,
        "ts": ts,
        "ts_utc": format_ts_utc(ts),
        "mark_lamports": mark,
        "ata_deposit_lamports": _DEPOSIT,
        "cost_basis_lamports": _COST,
    }


def _mark(ts: float, mark: int) -> dict[str, object]:
    return {
        "kind": "mark",
        "mint": _MINT,
        "ts": ts,
        "ts_utc": format_ts_utc(ts),
        "mark_lamports": mark,
    }


def _tick(ts: float) -> dict[str, object]:
    return {"kind": "tick", "mint": _MINT, "ts": ts, "ts_utc": format_ts_utc(ts), "price": 1}
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
