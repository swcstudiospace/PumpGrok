<<<<<<< HEAD
"""Strategy framework package (STR-01..06).

Four ids only (D-01): legacy_screening plus the three baselines. No LLM
client is reachable from this package (STR-05: the runtime is the only
entry point and it never imports the Grok gateway).
"""

from __future__ import annotations
=======
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
