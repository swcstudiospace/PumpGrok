"""Evidence grading for promotion eligibility (BT-10; CONTEXT D-05).

Only ``recorded + complete + long + gap-light`` data grades as promotion
evidence. ``traded_only``, ``fixture`` and ``hand-authored`` data never
grade as promotion evidence: they are useful for replay realism but
cannot prove a strategy earns. Look-ahead purity is enforced by the
point-in-time canary in the test suite: data stamped after a decision
time T must never change a decision made at or before T.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "GAP_LIGHT_MAX",
    "LONG_MIN_DAYS",
    "DataKind",
    "DatasetMeta",
    "GradeResult",
    "grade",
]

#: A dataset counts as "long" at or past this duration in days.
LONG_MIN_DAYS = 30.0

#: A dataset counts as "gap-light" at or below this many gaps.
GAP_LIGHT_MAX = 2


class DataKind(StrEnum):
    """Provenance of one dataset."""

    RECORDED = "recorded"
    TRADED_ONLY = "traded_only"
    FIXTURE = "fixture"
    HAND_AUTHORED = "hand-authored"


@dataclass(frozen=True)
class DatasetMeta:
    """Grading inputs: provenance, completeness, duration and gap count."""

    kind: DataKind
    complete: bool
    duration_days: float
    gap_count: int

    def __post_init__(self) -> None:
        if self.duration_days < 0:
            raise ValueError("duration_days must not be negative")
        if self.gap_count < 0:
            raise ValueError("gap_count must not be negative")


@dataclass(frozen=True)
class GradeResult:
    """Promotion-eligibility verdict with the failing reasons listed."""

    eligible: bool
    reasons: tuple[str, ...]


def grade(meta: DatasetMeta) -> GradeResult:
    """Grade dataset meta: eligible only for recorded, complete, long, gap-light.

    Every failing condition is listed in ``reasons``; an eligible dataset
    carries the single reason "pass".
    """
    reasons: list[str] = []
    if meta.kind != DataKind.RECORDED:
        reasons.append(f"kind {meta.kind} is not recorded")
    if not meta.complete:
        reasons.append("dataset is incomplete")
    if meta.duration_days < LONG_MIN_DAYS:
        reasons.append(f"duration {meta.duration_days} days is below {LONG_MIN_DAYS} days")
    if meta.gap_count > GAP_LIGHT_MAX:
        reasons.append(f"{meta.gap_count} gaps exceeds {GAP_LIGHT_MAX}")
    if not reasons:
        return GradeResult(eligible=True, reasons=("pass",))
    return GradeResult(eligible=False, reasons=tuple(reasons))
