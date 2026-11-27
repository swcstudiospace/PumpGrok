"""Gap segmentation, flatten haircut and the post-gap entry gate (BT-11).

Gaps come from a REC-02 gaps.jsonl and from event timestamp deltas above the
gap-light single-gap limit. The cooldown is a property of the segment: the
entry gate does not read a clock. A torn final line is dropped, as REC-02 does.
Realized P&L on a flatten excludes the ATA deposit refunded at close.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, overload

from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME

__all__ = [
    "GapFlag",
    "Segment",
    "Segmentation",
    "flatten_lamports",
    "gap_intervals",
    "segment",
]

_BPS = 10_000


@dataclass(frozen=True)
class Segment:
    """One tradable window. Entry is allowed only inside it, never by a clock."""

    start_ts: float
    end_ts: float

    def allows_entry(self, ts: float) -> bool:
        return self.start_ts <= ts < self.end_ts


@dataclass(frozen=True)
class GapFlag:
    """A position that was open when a gap started, flattened or excluded."""

    mint: str
    action: Literal["flatten", "exclude"]
    gap_start: float
    gap_end: float
    last_mark_lamports: int
    flatten_lamports: int | None
    refund_lamports: int
    realized_lamports: int | None


@dataclass(frozen=True)
class Segmentation:
    segments: tuple[Segment, ...]
    flags: tuple[GapFlag, ...]
    gap_intervals: tuple[tuple[float, float], ...]
    open_mints: tuple[str, ...]
    torn_tail_dropped: bool
    cooldown_s: float

    def entry_allowed(self, ts: float) -> bool:
        """True only when some segment's own gate admits ts. No clock is read."""
        return any(segment.allows_entry(ts) for segment in self.segments)


def flatten_lamports(last_mark: int, haircut_bps: int) -> int:
    """Last mark less the haircut, in integer lamports."""
    if isinstance(last_mark, bool) or not isinstance(last_mark, int):
        raise TypeError("last mark must be an int number of lamports")
    if isinstance(haircut_bps, bool) or not isinstance(haircut_bps, int):
        raise TypeError("haircut_bps must be an int")
    if last_mark < 0 or haircut_bps < 0 or haircut_bps > _BPS:
        raise ValueError("mark and haircut must be non-negative and within 10000 bps")
    return last_mark * (_BPS - haircut_bps) // _BPS


def segment(
    dataset: str | Path,
    gaps_jsonl: str | Path | None,
    cooldown_s: float,
    haircut_bps: int,
    *,
    exclude: bool = False,
) -> Segmentation:
    """Segment a dataset around gaps and flatten or exclude positions open at a gap.

    ``cooldown_s`` and ``haircut_bps`` are the caller's approved values. The
    single-gap delta limit is read from APPROVED_THRESHOLDS so it is not copied.
    """
    if isinstance(cooldown_s, bool) or not isinstance(cooldown_s, (int, float)):
        raise TypeError("cooldown_s must be a number of seconds")
    if cooldown_s < 0:
        raise ValueError("cooldown_s must be non-negative")

    # grading imports gap_intervals; a module import would cycle gaps <-> grading.
    from pumpgrok.backtest.grading import APPROVED_THRESHOLDS  # noqa: PLC0415

    root = Path(dataset)
    events = _read_events(root / EVENTS_NAME)
    intervals, torn = gap_intervals(
        events,
        gaps_jsonl,
        single_gap_s=APPROVED_THRESHOLDS.max_single_gap_s,
        report_torn=True,
    )
    flags, open_mints = _apply_positions(
        events, intervals, haircut_bps=haircut_bps, exclude=exclude
    )
    stamps = [stamp for event in events if (stamp := _event_ts(event)) is not None]
    span = (min(stamps), max(stamps)) if stamps else None
    segments = _segments(span, intervals, cooldown_s)
    return Segmentation(
        segments=segments,
        flags=flags,
        gap_intervals=intervals,
        open_mints=open_mints,
        torn_tail_dropped=torn,
        cooldown_s=float(cooldown_s),
    )


@overload
def gap_intervals(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    gaps_jsonl: str | Path | None,
    *,
    single_gap_s: float,
    report_torn: Literal[True],
) -> tuple[tuple[tuple[float, float], ...], bool]: ...


@overload
def gap_intervals(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    gaps_jsonl: str | Path | None,
    *,
    single_gap_s: float,
    report_torn: Literal[False] = False,
) -> tuple[tuple[float, float], ...]: ...


def gap_intervals(
    events: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    gaps_jsonl: str | Path | None,
    *,
    single_gap_s: float,
    report_torn: bool = False,
) -> tuple[tuple[float, float], ...] | tuple[tuple[tuple[float, float], ...], bool]:
    """Union of recorded gaps and timestamp deltas above ``single_gap_s``.

    A delta equal to the limit is not a gap. Recorded gaps count at any length.
    Overlaps are merged so a delta covered by gaps.jsonl is not counted twice.
    """
    recorded, torn = _read_gap_file(gaps_jsonl)
    found = list(recorded)
    stamps = sorted(stamp for event in events if (stamp := _event_ts(event)) is not None)
    for earlier, later in pairwise(stamps):
        if later - earlier > single_gap_s:
            found.append((earlier, later))
    merged = _merge(found)
    if report_torn:
        return merged, torn
    return merged


def _segments(
    span: tuple[float, float] | None,
    intervals: tuple[tuple[float, float], ...],
    cooldown_s: float,
) -> tuple[Segment, ...]:
    if span is None:
        return ()
    start, end = span
    blocked = _merge((gap_start, gap_end + cooldown_s) for gap_start, gap_end in intervals)
    cursor = start
    segments: list[Segment] = []
    for block_start, block_end in blocked:
        if block_end <= cursor or block_start >= end:
            continue
        if block_start > cursor:
            segments.append(Segment(cursor, min(block_start, end)))
        cursor = max(cursor, block_end)
    if cursor < end:
        segments.append(Segment(cursor, end))
    return tuple(segments)


def _apply_positions(
    events: tuple[dict[str, Any], ...],
    intervals: tuple[tuple[float, float], ...],
    *,
    haircut_bps: int,
    exclude: bool,
) -> tuple[tuple[GapFlag, ...], tuple[str, ...]]:
    open_positions: dict[str, dict[str, int]] = {}
    flags: list[GapFlag] = []
    ordered = sorted(events, key=lambda event: _event_ts(event) or 0.0)
    gap_at = 0
    for event in ordered:
        stamp = _event_ts(event)
        if stamp is None:
            continue
        # EXEC-EX-11: flatten only once the event is strictly past the gap start,
        # so an event stamped at the gap start applies before the flatten.
        while gap_at < len(intervals) and intervals[gap_at][0] < stamp:
            gap_start, gap_end = intervals[gap_at]
            flags.extend(
                _close_open(
                    open_positions,
                    gap_start=gap_start,
                    gap_end=gap_end,
                    haircut_bps=haircut_bps,
                    exclude=exclude,
                )
            )
            gap_at += 1
        _apply_event(open_positions, event)
    while gap_at < len(intervals):
        gap_start, gap_end = intervals[gap_at]
        flags.extend(
            _close_open(
                open_positions,
                gap_start=gap_start,
                gap_end=gap_end,
                haircut_bps=haircut_bps,
                exclude=exclude,
            )
        )
        gap_at += 1
    return tuple(flags), tuple(sorted(open_positions))


def _close_open(
    open_positions: dict[str, dict[str, int]],
    *,
    gap_start: float,
    gap_end: float,
    haircut_bps: int,
    exclude: bool,
) -> list[GapFlag]:
    # EXEC-EX-12: consumed is scoped to this call only, so a reopened mint's
    # later events are never invisible.
    consumed: set[str] = set()
    flags: list[GapFlag] = []
    for mint in sorted(open_positions):
        if mint in consumed:
            continue
        position = open_positions[mint]
        mark = position["mark"]
        refund = position["refund"]
        cost = position["cost"]
        if exclude:
            flags.append(
                GapFlag(
                    mint=mint,
                    action="exclude",
                    gap_start=gap_start,
                    gap_end=gap_end,
                    last_mark_lamports=mark,
                    flatten_lamports=None,
                    refund_lamports=refund,
                    realized_lamports=None,
                )
            )
        else:
            proceeds = flatten_lamports(mark, haircut_bps)
            # Refund returns to cash and is not profit. Cost still holds the deposit,
            # so realized is proceeds minus cost net of that refund.
            realized = proceeds - (cost - refund)
            flags.append(
                GapFlag(
                    mint=mint,
                    action="flatten",
                    gap_start=gap_start,
                    gap_end=gap_end,
                    last_mark_lamports=mark,
                    flatten_lamports=proceeds,
                    refund_lamports=refund,
                    realized_lamports=realized,
                )
            )
        consumed.add(mint)
    for mint in consumed:
        open_positions.pop(mint, None)
    return flags


def _apply_event(
    open_positions: dict[str, dict[str, int]],
    event: dict[str, Any],
) -> None:
    kind = event.get("kind")
    mint = event.get("mint")
    if not isinstance(mint, str):
        return
    if kind == "open":
        mark = _lamports(event.get("mark_lamports"), "mark")
        refund = _lamports(event.get("ata_deposit_lamports", 0), "deposit")
        cost = _lamports(event.get("cost_basis_lamports", mark + refund), "cost")
        open_positions[mint] = {"mark": mark, "refund": refund, "cost": cost}
    elif kind == "mark" and mint in open_positions:
        open_positions[mint]["mark"] = _lamports(event.get("mark_lamports"), "mark")
    elif kind == "close":
        open_positions.pop(mint, None)


def _lamports(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an int number of lamports")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _read_events(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.is_file():
        return ()
    data = path.read_bytes()
    rows: list[dict[str, Any]] = []
    lines = data.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError as err:
            # EXEC-EX-13: tolerate only an unterminated final fragment; anything
            # else is corruption that would hide a real gap, so refuse.
            is_final = index == len(lines) - 1 and not data.endswith(b"\n")
            if is_final:
                continue
            raise ValueError(f"malformed event line {index + 1} in {path}") from err
        if isinstance(raw, dict):
            rows.append(raw)
    return tuple(rows)


def _read_gap_file(gaps_jsonl: str | Path | None) -> tuple[tuple[tuple[float, float], ...], bool]:
    if gaps_jsonl is None:
        return (), False
    path = Path(gaps_jsonl)
    if not path.is_file():
        return (), False
    data, torn = _drop_torn_tail(path.read_bytes())
    return _gap_rows(data, torn)


def _drop_torn_tail(data: bytes) -> tuple[bytes, bool]:
    if not data or data.endswith(b"\n"):
        return data, False
    # EXEC-EX-14: a valid row missing only its newline is kept, not dropped.
    last_newline = data.rfind(b"\n")
    tail = data[last_newline + 1 :] if last_newline >= 0 else data
    if tail.strip():
        try:
            json.loads(tail)
        except ValueError:
            trimmed = data[: last_newline + 1] if last_newline >= 0 else b""
            return trimmed, True
    return data + b"\n", False


def _gap_rows(data: bytes, torn: bool) -> tuple[tuple[tuple[float, float], ...], bool]:
    intervals: list[tuple[float, float]] = []
    lines = data.splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except ValueError:
            if index == len(lines) - 1:
                torn = True
                continue
            raise
        interval = _gap_interval(raw)
        if interval is not None:
            intervals.append(interval)
    return tuple(intervals), torn


def _gap_interval(raw: object) -> tuple[float, float] | None:
    if not isinstance(raw, dict):
        return None
    start = _epoch(raw.get("start_ts_utc"))
    end = _epoch(raw.get("end_ts_utc"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _merge(intervals: Any) -> tuple[tuple[float, float], ...]:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    if not ordered:
        return ()
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return tuple((item[0], item[1]) for item in merged)


def _event_ts(event: dict[str, Any]) -> float | None:
    raw = event.get("ts")
    if not isinstance(raw, bool) and isinstance(raw, (int, float)):
        return float(raw)
    return _epoch(event.get("ts_utc"))


def _epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_ts_utc(value)
    except ValueError:
        return None
