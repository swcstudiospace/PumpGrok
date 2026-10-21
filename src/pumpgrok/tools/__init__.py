"""Typed tool layer composition root (STRUCT-002, TOOL-001..008).

`build_registry()` is the single place the CLI and the desk gateway obtain a
`ToolRegistry`: an injected clock (`FixtureClock` for replays, `WallClock` in
production), a list-backed audit sink owned by the caller, a fail-closed
limits checker that refuses every approval-gated call until RiskEngine lands
(Phase 4), and one `RateLimiter` per `rate_limit_key` held inside the
registry. Catalog tools register in later Phase 3 plans; the tracer proves
the slice with a test-only probe registered through the returned registry.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import random
from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import Clock
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.replay.clock import WallClock

__all__ = ["build_registry"]


async def _refuse_all(request: OrderRequest, bot_id: str) -> bool:
    """Fail-closed limits checker (skeleton): refuse until RiskEngine lands."""
    return False


def build_registry(
    clock: Clock | None = None,
    rng: random.Random | None = None,
) -> tuple[ToolRegistry, list[GrantAudit]]:
    """Build an empty registry with replay-safe defaults.

    Returns the registry plus the audit list backing its sink, so tests and
    the gateway can assert one row per resolution attempt (I4).
    """
    audits: list[GrantAudit] = []
    registry = ToolRegistry(
        clock=clock if clock is not None else WallClock(),
        audit_sink=audits.append,
        limits_checker=_refuse_all,
        rng=rng,
    )
    return registry, audits


# Re-exported for composition-root callers that type the checker explicitly.
LimitsChecker = Callable[[OrderRequest, str], Awaitable[bool]]
