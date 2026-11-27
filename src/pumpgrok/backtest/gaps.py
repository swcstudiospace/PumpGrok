"""Gap segmentation and haircut policy (BT-11; CONTEXT D-06).

A dataset is segmented at gaps: runs of silence longer than
``GAP_THRESHOLD_S`` split the timeline into segments. The policy is a
single constant, ``GAP_POLICY = "flatten_haircut"``: a position open at
a gap is flattened at the last pre-gap price with a 500 bps haircut, so
its realized net is haircut by that fraction of the exit lamports, and
no entries are allowed during a cooldown after the gap ends.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "GAP_HAIRCUT_BPS",
    "GAP_POLICY",
    "GAP_THRESHOLD_S",
    "GapSegment",
    "entries_allowed",
    "flatten_at_gaps",
    "segment_dataset",
]

#: Silence (seconds) after which a dataset is considered gapped.
GAP_THRESHOLD_S = 30.0

#: Haircut applied to an exit flattened at a gap, in basis points.
GAP_HAIRCUT_BPS = 500

#: The single gap policy: flatten open positions at the gap with haircut.
GAP_POLICY = "flatten_haircut"

#: No entries during this cooldown after a gap ends, in seconds.
COOLDOWN_S = 60.0


@dataclass(frozen=True)
class GapSegment:
    """One contiguous run between gaps: [start_ts, end_ts) plus event count."""

    start_ts: float
    end_ts: float
    size: int


def segment_dataset(stamps: Sequence[float]) -> tuple[GapSegment, ...]:
    """Split ordered stamps into segments at gaps wider than the threshold."""
    if not stamps:
        return ()
    segments: list[GapSegment] = []
    start = previous = stamps[0]
    size = 1
    for stamp in stamps[1:]:
        if stamp - previous > GAP_THRESHOLD_S:
            segments.append(GapSegment(start_ts=start, end_ts=previous, size=size))
            start = stamp
            size = 0
        previous = stamp
        size += 1
    segments.append(GapSegment(start_ts=start, end_ts=previous, size=size))
    return tuple(segments)


def flatten_at_gaps(exit_lamports: int) -> int:
    """Haircut exit lamports by 500 bps, rounding towards zero (integer math)."""
    haircut = exit_lamports * GAP_HAIRCUT_BPS // 10_000
    return exit_lamports - haircut


def entries_allowed(
    ts: float, gaps: Sequence[tuple[float, float]], cooldown_s: float = COOLDOWN_S
) -> bool:
    """False during a gap or its cooldown; True otherwise."""
    return all(not start <= ts < end + cooldown_s for start, end in gaps)
