<<<<<<< HEAD
"""Evidence grading for promotion eligibility (BT-10; CONTEXT D-05).

Only ``recorded + complete + long + gap-light`` data grades as promotion
evidence. ``traded_only``, ``fixture`` and ``hand-authored`` data never
grade as promotion evidence: they are useful for replay realism but
cannot prove a strategy earns. Look-ahead purity is enforced by the
point-in-time canary in the test suite: data stamped after a decision
time T must never change a decision made at or before T.
=======
"""Evidence grading for promotion (BT-10).

Only a recorded, sealed, long, gap-light dataset with a passing look-ahead canary
grades promotion_eligible. Threshold numbers live only on APPROVED_THRESHOLDS.
The haircut is ROADMAP criterion 4, not an owner-approved threshold; it is stored
here so no second copy is written.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
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
=======
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import EVENTS_NAME, MANIFEST_NAME, load_dataset

__all__ = [
    "APPROVED_THRESHOLDS",
    "CanaryResult",
    "Grade",
    "Thresholds",
    "grade",
]

_BPS = 10_000
_HAND_AUTHORED = "hand-authored"
_REASONS = (
    "canary",
    "fixture",
    "gap",
    "hand_authored",
    "short",
    "synthetic",
    "traded_only",
    "unsealed",
)


@dataclass(frozen=True)
class Thresholds:
    """The one copy of the grading and gap numbers."""

    long_s: int
    max_single_gap_s: int
    max_total_gap_numerator: int
    max_total_gap_denominator: int
    cooldown_s: int
    haircut_bps: int

    def __post_init__(self) -> None:
        if self.max_total_gap_denominator <= 0:
            raise ValueError("gap fraction denominator must be positive")
        if self.haircut_bps < 0 or self.haircut_bps > _BPS:
            raise ValueError("haircut must be between 0 and 10000 bps")


#: Approved 2026-11-16, plus the ROADMAP haircut so it is not copied elsewhere.
APPROVED_THRESHOLDS = Thresholds(
    long_s=604_800,
    max_single_gap_s=300,
    max_total_gap_numerator=5,
    max_total_gap_denominator=100,
    cooldown_s=300,
    haircut_bps=500,
)


@dataclass(frozen=True)
class CanaryResult:
    """Whether data after time T left every decision at or before T unchanged."""

    passed: bool


@dataclass(frozen=True)
class Grade:
    """promotion_eligible, or research_only with every failing reason, sorted."""

    verdict: Literal["promotion_eligible", "research_only"]
    reasons: tuple[str, ...]


def grade(dataset: str | Path, canary_result: CanaryResult, thresholds: Thresholds) -> Grade:
    """Grade one dataset. Promotion requires every condition; otherwise research_only."""
    path = Path(dataset)
    reasons = _collect_reasons(path, canary_result, thresholds)
    unknown = reasons - set(_REASONS)
    if unknown:
        raise RuntimeError(f"unknown grade reasons: {sorted(unknown)}")
    ordered = tuple(reason for reason in _REASONS if reason in reasons)
    if ordered:
        return Grade("research_only", ordered)
    return Grade("promotion_eligible", ())


def _collect_reasons(path: Path, canary_result: CanaryResult, thresholds: Thresholds) -> set[str]:
    reasons: set[str] = set()
    if not isinstance(canary_result, CanaryResult) or not canary_result.passed:
        reasons.add("canary")
    manifest, events, sealed = _load(path)
    reasons.update(_provenance_reasons(path, manifest, events, sealed))
    window = _window_s(manifest, events)
    if window is None or window < thresholds.long_s:
        reasons.add("short")
    if not _gap_light(path, events, window, thresholds):
        reasons.add("gap")
    return reasons


def _provenance_reasons(
    path: Path,
    manifest: dict[str, Any] | None,
    events: tuple[dict[str, Any], ...],
    sealed: bool,
) -> set[str]:
    reasons: set[str] = set()
    if not sealed:
        reasons.add("unsealed")
    if _is_fixture(path, manifest):
        reasons.add("fixture")
    if _is_hand_authored(manifest):
        reasons.add("hand_authored")
    if _is_synthetic(path, manifest):
        reasons.add("synthetic")
    if _has_traded_only(events):
        reasons.add("traded_only")
    return reasons


def _load(
    path: Path,
) -> tuple[dict[str, Any] | None, tuple[dict[str, Any], ...], bool]:
    try:
        dataset = load_dataset(path)
    except Exception:
        return _loose_manifest(path), _loose_events(path), False
    manifest = dataset.manifest.model_dump()
    return manifest, dataset.events, True


def _loose_manifest(path: Path) -> dict[str, Any] | None:
    target = path / MANIFEST_NAME
    if not target.is_file():
        return None
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def _loose_events(path: Path) -> tuple[dict[str, Any], ...]:
    target = path / EVENTS_NAME
    if not target.is_file():
        return ()
    rows: list[dict[str, Any]] = []
    try:
        for line in target.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            if isinstance(raw, dict):
                rows.append(raw)
    except (OSError, UnicodeDecodeError, ValueError):
        return tuple(rows)
    return tuple(rows)


def _is_fixture(path: Path, manifest: dict[str, Any] | None) -> bool:
    name = path.name
    if manifest is not None and isinstance(manifest.get("dataset"), str):
        name = manifest["dataset"]
    return name.startswith("smoke")


def _is_hand_authored(manifest: dict[str, Any] | None) -> bool:
    if manifest is None:
        return False
    notes = manifest.get("notes")
    if isinstance(notes, str) and _HAND_AUTHORED in notes.lower():
        return True
    sources = manifest.get("sources")
    if isinstance(sources, dict):
        for value in sources.values():
            if isinstance(value, str) and _HAND_AUTHORED in value.lower():
                return True
    return False


def _is_synthetic(path: Path, manifest: dict[str, Any] | None) -> bool:
    """Recorded provenance does not rescue a dataset built under the temp root."""
    if _under_temp(path):
        return True
    if manifest is None:
        return False
    return manifest.get("provenance") == "synthetic"


def _under_temp(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    root = Path(tempfile.gettempdir()).resolve()
    return resolved == root or root in resolved.parents


def _has_traded_only(events: tuple[dict[str, Any], ...]) -> bool:
    for event in events:
        if event.get("traded_only") is True:
            return True
        if event.get("coverage") == "traded_only":
            return True
    return False


def _window_s(manifest: dict[str, Any] | None, events: tuple[dict[str, Any], ...]) -> float | None:
    if manifest is not None:
        start = _epoch(manifest.get("recorded_from_utc"))
        end = _epoch(manifest.get("recorded_to_utc"))
        if start is not None and end is not None and end >= start:
            return end - start
    stamps = [stamp for event in events if (stamp := _event_ts(event)) is not None]
    if len(stamps) < 2:
        return None
    return max(stamps) - min(stamps)


def _gap_light(
    path: Path,
    events: tuple[dict[str, Any], ...],
    window: float | None,
    thresholds: Thresholds,
) -> bool:
    if window is None or window <= 0:
        return False
    # gaps.segment imports APPROVED_THRESHOLDS; a module import would cycle grading <-> gaps.
    from pumpgrok.backtest.gaps import gap_intervals  # noqa: PLC0415

    intervals = gap_intervals(
        events,
        path / "gaps.jsonl",
        single_gap_s=thresholds.max_single_gap_s,
    )
    total = 0.0
    for start, end in intervals:
        length = end - start
        if length > thresholds.max_single_gap_s:
            return False
        total += length
    budget = window * thresholds.max_total_gap_numerator / thresholds.max_total_gap_denominator
    return total <= budget


def _event_ts(event: dict[str, Any]) -> float | None:
    raw = event.get("ts")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return _epoch(event.get("ts_utc"))
    return float(raw)


def _epoch(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_ts_utc(value)
    except ValueError:
        return None
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
