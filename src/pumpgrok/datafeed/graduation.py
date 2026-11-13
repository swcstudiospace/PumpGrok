"""Paper-only decisions for curve graduation and unavailable-price gaps.

These decisions do not place orders or change positions. A timeout requests a
zero accounting mark, not a simulated sale; graduation is a separate signal.

A fixture snapshot admits only when the caller passes the :class:`VerifiedReplay`
whose dataset the snapshot was read from. A source label alone never admits.
"""

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.replay.fixtures import event_epoch
from pumpgrok.tools.onchain import curve_layout

if TYPE_CHECKING:
    from pumpgrok.execution.paper_factory import VerifiedReplay


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


def _is_reserve(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bound_tick(snapshot: CurveSnapshot, replay: "VerifiedReplay") -> bool:
    """True when ``snapshot`` equals a tick of the dataset ``replay`` verified.

    A hand-built snapshot that only carries the ``fixture`` label matches no
    verified tick and is refused.
    """
    stamp = snapshot.ts
    if stamp is None or not math.isfinite(stamp):
        return False
    for event in replay.dataset.events:
        if event.get("mint") != snapshot.mint:
            continue
        s, t = event.get("S"), event.get("T")
        if not (_is_reserve(s) and _is_reserve(t)):
            continue
        if (
            (s, t) == (snapshot.s_lamports, snapshot.t_units)
            and bool(event.get("complete", False)) == snapshot.complete
            and event_epoch(event) == stamp
        ):
            return True
    return False


def _provenance(
    snapshot: CurveSnapshot, replay: "VerifiedReplay | None"
) -> curve_layout.CurveProvenance:
    """Honest origin of a snapshot, from what the caller can prove.

    ``rpc`` is a live feed read. A fixture read is VERIFIED_REPLAY only when the
    caller holds the verified binding and the snapshot is one of its ticks.
    Anything else is UNKNOWN and fails closed.
    """
    if snapshot.source == "rpc":
        return curve_layout.CurveProvenance.LIVE_RPC
    if (
        replay is not None
        and snapshot.source == curve_layout.VERIFIED_REPLAY_SOURCE
        and _is_bound_tick(snapshot, replay)
    ):
        return curve_layout.CurveProvenance.VERIFIED_REPLAY
    return curve_layout.CurveProvenance.UNKNOWN


def _admitted(snapshot: CurveSnapshot, replay: "VerifiedReplay | None") -> bool:
    return (
        snapshot.source in {"fixture", "rpc"}
        and snapshot.s_lamports > 0
        and snapshot.t_units > 0
        and curve_layout.rpc_curve_price_allowed(
            curve_source=snapshot.source, provenance=_provenance(snapshot, replay)
        )
    )


def entry_allowed(
    snapshot: CurveSnapshot | None,
    *,
    now: float,
    max_age_s: float,
    replay: "VerifiedReplay | None" = None,
) -> bool:
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
        and _admitted(snapshot, replay)
        and snapshot.ts is not None
        and math.isfinite(snapshot.ts)
        and 0 <= now - snapshot.ts <= max_age_s
    )


def position_action(
    snapshot: CurveSnapshot | None,
    *,
    last_trusted_at: float,
    now: float,
    settings: GapSettings,
    replay: "VerifiedReplay | None" = None,
) -> PositionAction:
    """Select a mark, hold, zero mark, or graduated signal without executing it.

    The caller supplies the time of the last fresh trusted observation and
    current injected clock time. Stale input never extends that deadline.
    """
    if not math.isfinite(now) or not math.isfinite(last_trusted_at) or last_trusted_at > now:
        raise ValueError("timestamps must be finite and last_trusted_at must not be future")
    if snapshot is not None and _admitted(snapshot, replay):
        stamp = snapshot.ts
        if stamp is not None and math.isfinite(stamp) and 0 <= now - stamp <= settings.gap_after_s:
            return PositionAction.GRADUATED if snapshot.complete else PositionAction.MARK
    if now - last_trusted_at >= settings.timeout_after_s:
        return PositionAction.ZERO_MARK
    return PositionAction.HOLD
