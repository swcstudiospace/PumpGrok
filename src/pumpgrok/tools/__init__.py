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

import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pumpgrok.core.adapter import OrderRequest
from pumpgrok.core.ids import Clock
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.replay.clock import WallClock

if TYPE_CHECKING:
    from pumpgrok.tools.onchain.rpc import RpcClient

__all__ = ["build_registry", "register_read_tools"]


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


def register_read_tools(registry: ToolRegistry, rpc: RpcClient) -> ToolRegistry:
    """Register the twelve wave-2 READ tools bound to one RPC client.

    Market (TOOL-001) and onchain (TOOL-002) tools share the single
    ``RpcClient`` with ordered failover and a header-only key (T-03-02-02).
    Returns the registry for chaining.
    """
    from pumpgrok.tools.market.holders_snapshot import build_holders_snapshot_tool
    from pumpgrok.tools.market.liquidity import build_liquidity_tool
    from pumpgrok.tools.market.ohlcv import build_ohlcv_tool
    from pumpgrok.tools.market.price import build_price_tool
    from pumpgrok.tools.market.trades import build_trades_tool
    from pumpgrok.tools.onchain.authorities_tool import build_authorities_tool
    from pumpgrok.tools.onchain.deployer_history import build_deployer_history_tool
    from pumpgrok.tools.onchain.large_transfers import build_large_transfers_tool
    from pumpgrok.tools.onchain.lp_status import build_lp_status_tool
    from pumpgrok.tools.onchain.priority_fee_tool import build_priority_fee_tool
    from pumpgrok.tools.onchain.token_metadata import build_token_metadata_tool
    from pumpgrok.tools.onchain.top_holders import build_top_holders_tool

    registry.register_all(
        [
            build_price_tool(rpc),
            build_ohlcv_tool(rpc),
            build_liquidity_tool(rpc),
            build_trades_tool(rpc),
            build_holders_snapshot_tool(rpc),
            build_token_metadata_tool(rpc),
            build_authorities_tool(rpc),
            build_lp_status_tool(rpc),
            build_top_holders_tool(rpc),
            build_deployer_history_tool(rpc),
            build_large_transfers_tool(rpc),
            build_priority_fee_tool(rpc),
        ]
    )
    return registry
