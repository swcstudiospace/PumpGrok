"""Side-effect classes for tools (interfaces.md 2.1)."""

from __future__ import annotations

import enum


class SideEffect(enum.StrEnum):
    """Side-effect class of a tool. Ordered: READ < PAPER_WRITE < LIVE_WRITE.

    LIVE_WRITE exists only so the registry can name what it refuses (D3, D4).
    """

    READ = "read"
    PAPER_WRITE = "paper-write"
    LIVE_WRITE = "live-write"

    @property
    def rank(self) -> int:
        return _SIDE_EFFECT_RANK[self]

    def exceeds(self, other: SideEffect) -> bool:
        return self.rank > other.rank


_SIDE_EFFECT_RANK: dict[SideEffect, int] = {
    SideEffect.READ: 0,
    SideEffect.PAPER_WRITE: 1,
    SideEffect.LIVE_WRITE: 2,
}

# The highest side effect any seat may ever be granted. Not configurable.
MAX_GRANTABLE_SIDE_EFFECT: SideEffect = SideEffect.PAPER_WRITE
