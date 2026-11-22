"""Resync: seed exactly the held mints through the supervisor (MKT-06).

A corrupt cursor starts clean (the supervisor owns that path).
"""

from __future__ import annotations

from typing import Any

from pumpgrok.datafeed.mintbook import MintBook


def resync_held(supervisor: Any, book: MintBook) -> tuple[str, ...]:
    """Seed the supervisor with exactly the held mints; return the seed."""
    held = tuple(sorted(book.held()))
    supervisor.resync(held)
    return held
