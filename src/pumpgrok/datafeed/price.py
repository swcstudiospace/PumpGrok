"""Fail-closed live price source (MKT-07, T-13-02a).

No network call inside: the caller feeds ticks/gaps. Disconnected yields
None; a completed curve refuses entry via :mod:`pumpgrok.datafeed.graduation`;
a gap holds the last good value (marked stale, never reused as new); a
timeout marks zero. Every call consults ``rpc_curve_price_allowed``.
"""

from __future__ import annotations

import logging
import math
from collections import OrderedDict
from collections.abc import Callable
from typing import Final

from pumpgrok.datafeed.events import CurveObservation, CurveTick, GapEvent
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.execution.paper_adapter.models import CurveSnapshot
from pumpgrok.replay.clock import Clock, parse_ts_utc
from pumpgrok.tools.onchain.curve_layout import CurveProvenance, rpc_curve_price_allowed

log = logging.getLogger(__name__)

#: The only label live observations carry. Every live snapshot is stamped with it.
LIVE_SOURCE: Final[str] = "rpc"


class LivePriceSource:
    """Thin wrapper over the observation stream and the allowlist price gate."""

    def __init__(
        self, *, clock: Clock, health: SourceSupervisor, max_age_s: float, max_observations: int
    ) -> None:
        if isinstance(max_age_s, bool) or not isinstance(max_age_s, (int, float)):
            raise ValueError("max_age_s must be a positive finite number")
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("max_age_s must be a positive finite number")
        if type(max_observations) is not int or max_observations <= 0:
            raise ValueError("max_observations must be a positive integer")
        self._clock = clock
        self._health = health
        self._max_age_s = max_age_s
        self._max_observations = max_observations
        self._observations: dict[str, tuple[float, CurveObservation, int]] = {}
        self._observer: Callable[[CurveSnapshot], None] | None = None
        self.observer_failures = 0
        self._ticks: dict[str, CurveTick] = {}
        self._gaps: set[str] = set()
        self._last_seen: dict[str, float] = {}

    def set_observer(self, observer: Callable[[CurveSnapshot], None] | None) -> None:
        """Install a synchronous observer of each snapshot curve() is about to return."""
        if observer is not None and not callable(observer):
            raise TypeError("observer must be callable or None")
        self._observer = observer

    def observe(self, observation: CurveObservation) -> None:
        """Store a validated live frame; fail explicitly if fresh-mint capacity is full.

        Only frames carrying the live label are stored. Fixture or unknown labels never
        occupy live state, so they cannot be priced later under any label.
        """
        stamp = observation.validate()
        if observation.source != LIVE_SOURCE:
            return
        now = self._clock.now()
        if (
            not math.isfinite(now)
            or stamp > now
            or self._health.status_at(now) is not SourceStatus.live
        ):
            return
        generation = self._health.connection_generation
        previous = self._observations.get(observation.mint)
        if previous is None and len(self._observations) >= self._max_observations:
            expired = [
                mint
                for mint, (old_stamp, _, old_generation) in self._observations.items()
                if old_generation != generation or now - old_stamp > self._max_age_s
            ]
            for mint in expired:
                del self._observations[mint]
            if len(self._observations) >= self._max_observations:
                raise OverflowError("live observation capacity exhausted")
        if previous is None or previous[2] != generation or stamp >= previous[0]:
            self._observations[observation.mint] = (stamp, observation, generation)

    def on_tick(self, tick: CurveTick) -> None:
        self._ticks[tick.mint] = tick
        self._gaps.discard(tick.mint)
        self._last_seen[tick.mint] = parse_ts_utc(tick.ts_utc)

    def on_gap(self, gap: GapEvent) -> None:
        if gap.mint is not None:
            self._gaps.add(gap.mint)

    def is_stale(self, mint: str) -> bool:
        """True while a gap holds the position (last good kept, not new)."""
        return mint in self._gaps

    def entry_allowed(self, mint: str) -> bool:
        """False when the mint has no tick, the source is barred, or the curve is complete."""
        tick = self._ticks.get(mint)
        if tick is None:
            return False
        provenance = (
            CurveProvenance.LIVE_RPC if tick.curve_source == "rpc" else CurveProvenance.UNKNOWN
        )
        if not rpc_curve_price_allowed(curve_source=tick.curve_source, provenance=provenance):
            return False
        return not tick.complete

    async def curve(self, mint: str) -> CurveSnapshot | None:
        """Return the latest admitted live snapshot for ``mint``, or None.

        Stale, future, wrong-generation or non-live observations are refused; a failed
        observer never changes the admission result.
        """
        now = self._clock.now()
        current = self._observations.get(mint)
        if current is None:
            return None
        stamp, observation, generation = current
        if (
            stamp > now
            or generation != self._health.connection_generation
            or now - stamp > self._max_age_s
            or observation.source != LIVE_SOURCE
        ):
            return None
        snapshot = CurveSnapshot(
            mint=observation.mint,
            s_lamports=observation.s_lamports,
            t_units=observation.t_units,
            complete=observation.complete,
            source=LIVE_SOURCE,
            ts=stamp,
        )
        if self._observer is not None:
            try:
                self._observer(snapshot)
            except Exception:  # an observer must never change admission
                self.observer_failures += 1
                log.exception("live price observer failed; admission unchanged")
        return snapshot


class ReservesCache:
    """Bounded latest-reserves map shared by the risk engine and the live observer.

    Eviction is least-recently-stored. Reserves are integer base units; a
    non-positive or non-integer pair is refused rather than stored.
    """

    def __init__(self, *, capacity: int) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        self._capacity = capacity
        self._entries: OrderedDict[str, tuple[int, int]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def observe(self, snapshot: CurveSnapshot) -> None:
        """Record the reserves of a snapshot the live source is returning."""
        self.store(snapshot.mint, snapshot.s_lamports, snapshot.t_units)

    def store(self, mint: str, s_lamports: int, t_units: int) -> None:
        if (
            type(s_lamports) is not int
            or s_lamports <= 0
            or type(t_units) is not int
            or t_units <= 0
        ):
            raise ValueError("reserves must be positive integers")
        self._entries[mint] = (s_lamports, t_units)
        self._entries.move_to_end(mint)
        while len(self._entries) > self._capacity:
            self._entries.popitem(last=False)

    def get(self, mint: str) -> tuple[int, int] | None:
        return self._entries.get(mint)
