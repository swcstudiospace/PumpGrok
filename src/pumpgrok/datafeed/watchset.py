"""Bounded watch set (MKT-05, T-13-01a). Held mints are pinned, never evicted."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class WatchSet:
    """At most ``cap`` watched mints. Pinned mints never evict; overflow is counted."""

    def __init__(self, cap: int) -> None:
        if cap < 1:
            raise ValueError("watch cap must be at least 1")
        self._cap = cap
        self._watched: set[str] = set()
        self._pinned: set[str] = set()
        self._overflow = 0

    @property
    def cap(self) -> int:
        return self._cap

    @property
    def overflow(self) -> int:
        return self._overflow

    def __len__(self) -> int:
        return len(self._watched)

    def watched(self) -> frozenset[str]:
        return frozenset(self._watched)

    def pin(self, mint: str) -> bool:
        """Pin a held mint so discoveries can never evict it."""
        self._pinned.add(mint)
        self._watched.add(mint)
        return True

    def unpin(self, mint: str) -> None:
        self._pinned.discard(mint)

    def is_pinned(self, mint: str) -> bool:
        return mint in self._pinned

    def discover(self, mint: str) -> bool:
        """Offer a new discovery. Beyond the cap: counted, logged, never dropped silently."""
        if mint in self._watched:
            return True
        if len(self._watched) >= self._cap:
            self._overflow += 1
            logger.warning("watch overflow: %s not watched (%d)", mint, self._overflow)
            return False
        self._watched.add(mint)
        return True

    def remove(self, mint: str) -> bool:
        """Remove an unpinned mint. Pinned mints refuse removal by returning False."""
        if mint in self._pinned:
            return False
        self._watched.discard(mint)
        return True
