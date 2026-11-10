"""Read-only live curve observations guarded by source health and freshness."""

import math

from pumpgrok.core.ids import Clock
from pumpgrok.datafeed.events import CurveObservation
from pumpgrok.events.sources import SourceStatus, SourceSupervisor
from pumpgrok.execution.paper_adapter.models import CurveSnapshot


class LivePriceSource:
    """Expose fresh RPC observations for paper execution and protective exits.

    Source provenance remains RPC; entry admission and trusted marking must
    independently consult the current review status.
    """

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

    def observe(self, observation: CurveObservation) -> None:
        """Store a validated frame; fail explicitly if fresh-mint capacity is full."""
        stamp = observation.validate()
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

    async def curve(self, mint: str) -> CurveSnapshot | None:
        now = self._clock.now()
        frame = self._health.last_frame_at
        if not math.isfinite(now) or frame is None or not math.isfinite(frame) or frame > now:
            return None
        if self._health.status_at(now) is not SourceStatus.live:
            self._observations.clear()
            return None
        current = self._observations.get(mint)
        if current is None:
            return None
        stamp, observation, generation = current
        if (
            stamp > now
            or generation != self._health.connection_generation
            or now - stamp > self._max_age_s
            or observation.source != "rpc"
        ):
            return None
        return CurveSnapshot(
            mint=observation.mint,
            s_lamports=observation.s_lamports,
            t_units=observation.t_units,
            complete=observation.complete,
            source=observation.source,
            ts=stamp,
        )
