"""Fallback: degraded behavior is honest; no transport, no ticks.

A source with no live transport yields stale, never invented ticks.
"""

from __future__ import annotations

from typing import Any


class FeedFallback:
    """REST/observations fallback. ``transport`` may be None (fully degraded)."""

    def __init__(self, transport: Any = None) -> None:
        self._transport = transport

    @property
    def has_transport(self) -> bool:
        return self._transport is not None

    def read(self) -> tuple[bool, list[Any]]:
        """(stale, ticks): stale True and no ticks when there is no transport."""
        if self._transport is None:
            return (True, [])
        return (False, [])
