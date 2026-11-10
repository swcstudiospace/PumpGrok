"""Temporary typed interface for graduation and unavailable-price decisions."""

from dataclasses import dataclass
from enum import StrEnum

from pumpgrok.execution.paper_adapter.models import CurveSnapshot


class PositionAction(StrEnum):
    MARK = "mark"
    HOLD = "hold"
    ZERO_MARK = "zero_mark"
    GRADUATED = "graduated"


@dataclass(frozen=True)
class GapSettings:
    gap_after_s: float
    timeout_after_s: float


def entry_allowed(snapshot: CurveSnapshot | None) -> bool:
    return False


def position_action(
    snapshot: CurveSnapshot | None, *, last_trusted_at: float, now: float, settings: GapSettings
) -> PositionAction | None:
    return None
