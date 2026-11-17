"""Strategy framework: protocol, read-only context, Intent, version id, static registry (STR-01)."""

from __future__ import annotations

from pumpgrok.strategies.base import (
    Intent,
    Side,
    Strategy,
    StrategyContext,
    TapePoint,
    TickSnapshot,
    source_digest,
    version_id,
)

__all__ = [
    "Intent",
    "Side",
    "Strategy",
    "StrategyContext",
    "TapePoint",
    "TickSnapshot",
    "source_digest",
    "version_id",
]
