"""Deterministic bus and journal rollup (EVT-08, RT-01).

`DeterministicBus` is the Phase 12 drain under `fixture_compat`: identical
bytes for identical inputs, exact hash equality, no tolerance band.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from pumpgrok.events.drain import DrainBytes, drain
from pumpgrok.events.models import Event
from pumpgrok.replay.clock import FixtureClock

#: Seed pinned by the smoke datasets (manifest seed_hint).
FIXTURE_SEED = 20260101


class DeterministicBus:
    """The Phase 12 drain as a bus. Only this drain is used; no second copy."""

    def __init__(self, *, clock: FixtureClock, rng: random.Random) -> None:
        self._clock = clock
        self._rng = rng

    def deliver(self, events: Sequence[Event], *, fixture_compat: bool = True) -> DrainBytes:
        if not fixture_compat:
            raise ValueError("deterministic bus requires fixture_compat")
        return drain(events, self._clock, self._rng)
