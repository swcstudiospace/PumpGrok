"""Bounded watch set: held mints are pinned, candidates overflow deterministically.

Held mints are open positions and are never dropped to make room for a candidate.
When a held pin needs a slot and the set is full of candidates, the newest candidate
is displaced and counted. A held pin is refused only when the held set alone is at
capacity; the refusal is counted and the set reports itself degraded.
"""

from __future__ import annotations


def _check_mint(mint: object) -> str:
    if not isinstance(mint, str) or not mint.strip():
        raise ValueError("mint must be a nonempty string")
    return mint


class WatchSet:
    def __init__(self, *, max_watched_mints: int) -> None:
        if type(max_watched_mints) is not int or max_watched_mints <= 0:
            raise ValueError("max_watched_mints must be a positive integer")
        self._capacity = max_watched_mints
        self._held: dict[str, None] = {}
        self._candidates: dict[str, None] = {}
        self._overflow = 0
        self._displaced = 0
        self._refused_held = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def held(self) -> tuple[str, ...]:
        return tuple(self._held)

    @property
    def candidates(self) -> tuple[str, ...]:
        return tuple(self._candidates)

    @property
    def overflow(self) -> int:
        """Candidate admissions refused because the set was full."""
        return self._overflow

    @property
    def displaced(self) -> int:
        """Candidates evicted to make room for a held pin."""
        return self._displaced

    @property
    def refused_held(self) -> int:
        """Held pins refused because the held set was already at capacity."""
        return self._refused_held

    @property
    def degraded(self) -> bool:
        return self._refused_held > 0

    def __contains__(self, mint: object) -> bool:
        return mint in self._held or mint in self._candidates

    def _total(self) -> int:
        return len(self._held) + len(self._candidates)

    def admit_candidate(self, mint: str) -> bool:
        """Watch a candidate. Returns False and counts overflow when the set is full."""
        _check_mint(mint)
        if mint in self:
            return True
        if self._total() >= self._capacity:
            self._overflow += 1
            return False
        self._candidates[mint] = None
        return True

    def pin(self, mint: str) -> bool:
        """Hold a mint. Returns False and signals degraded when the held set is full."""
        _check_mint(mint)
        if mint in self._held:
            return True
        if len(self._held) >= self._capacity:
            self._refused_held += 1
            return False
        self._candidates.pop(mint, None)
        if self._total() >= self._capacity:
            newest = next(reversed(self._candidates))
            del self._candidates[newest]
            self._displaced += 1
        self._held[mint] = None
        return True

    def release(self, mint: str) -> None:
        """Stop watching a mint, held or candidate. Frees its slot."""
        self._held.pop(mint, None)
        self._candidates.pop(mint, None)
