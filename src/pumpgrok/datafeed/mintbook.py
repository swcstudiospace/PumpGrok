"""Held-mint ledger consulted by resync and the marks loop (MKT-05)."""

from __future__ import annotations


class MintBook:
    """Set of mints currently held. Pure bookkeeping; no ledger or network access."""

    def __init__(self) -> None:
        self._held: set[str] = set()

    def hold(self, mint: str) -> None:
        self._held.add(mint)

    def release(self, mint: str) -> None:
        self._held.discard(mint)

    def is_held(self, mint: str) -> bool:
        return mint in self._held

    def held(self) -> frozenset[str]:
        return frozenset(self._held)

    def __len__(self) -> int:
        return len(self._held)

    def __bool__(self) -> bool:
        return bool(self._held)
