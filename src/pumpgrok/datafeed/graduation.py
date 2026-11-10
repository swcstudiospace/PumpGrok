"""Paper-only decisions for curve graduation and unavailable-price gaps.

These decisions do not place orders or change positions. A timeout requests a
zero accounting mark, not a simulated sale; graduation is a separate signal.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.tools.onchain import curve_layout


class PositionAction(StrEnum):
    MARK = "mark"
    HOLD = "hold"
    ZERO_MARK = "zero_mark"
    GRADUATED = "graduated"


@dataclass(frozen=True)
class GapSettings:
    """Explicit positive freshness and timeout budgets in seconds."""

    gap_after_s: float
    timeout_after_s: float

    def __post_init__(self) -> None:
        for value in (self.gap_after_s, self.timeout_after_s):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("gap and timeout must be positive finite seconds")
        if self.timeout_after_s < self.gap_after_s:
            raise ValueError("timeout must not precede the gap threshold")


def _admitted(snapshot: CurveSnapshot) -> bool:
    return (
        snapshot.source in {"fixture", "rpc"}
        and snapshot.s_lamports > 0
        and snapshot.t_units > 0
        and curve_layout.rpc_curve_price_allowed(curve_source=snapshot.source)
    )


def entry_allowed(snapshot: CurveSnapshot | None, *, now: float, max_age_s: float) -> bool:
    """Authorize only a fresh, admitted, incomplete paper entry observation."""
    if (
        isinstance(max_age_s, bool)
        or not isinstance(max_age_s, (int, float))
        or not math.isfinite(max_age_s)
        or max_age_s <= 0
        or not math.isfinite(now)
    ):
        raise ValueError("entry time and freshness budget must be finite and valid")
    return (
        snapshot is not None
        and not snapshot.complete
        and _admitted(snapshot)
        and snapshot.ts is not None
        and math.isfinite(snapshot.ts)
        and 0 <= now - snapshot.ts <= max_age_s
    )


def position_action(
    snapshot: CurveSnapshot | None, *, last_trusted_at: float, now: float, settings: GapSettings
) -> PositionAction:
    """Select a mark, hold, zero mark, or graduated signal without executing it.

    The caller supplies the time of the last fresh trusted observation and
    current injected clock time. Stale input never extends that deadline.
    """
    if not math.isfinite(now) or not math.isfinite(last_trusted_at) or last_trusted_at > now:
        raise ValueError("timestamps must be finite and last_trusted_at must not be future")
    if snapshot is not None and _admitted(snapshot):
        stamp = snapshot.ts
        if stamp is not None and math.isfinite(stamp) and 0 <= now - stamp <= settings.gap_after_s:
            return PositionAction.GRADUATED if snapshot.complete else PositionAction.MARK
    if now - last_trusted_at >= settings.timeout_after_s:
        return PositionAction.ZERO_MARK
    return PositionAction.HOLD
