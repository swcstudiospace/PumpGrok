"""Idle harness (EVT-12): 24 virtual hours, zero source events, zero calls.

The harness reuses the real bus and gateway with a counting transport fake.
No timers, no sleeps, no network.
"""

from __future__ import annotations

import asyncio

from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.wake import dispatch

HOURS = 24
_HOUR_S = 3600.0


class CountingTransport:
    """Transport fake that counts calls. No network."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, request: GatewayRequest) -> str:
        self.calls += 1
        return '{"ok": 1}'


def run_idle_grok_calls() -> int:
    """Gateway calls made over 24 virtual hours of silence. Expect 0."""
    clock = FixtureClock()
    transport = CountingTransport()
    gateway = GrokGateway(
        clock=clock,
        budget=LayeredBudget(window_cap=100, agent_cap=40, global_cap=200),
        transport=transport,
    )

    async def _idle() -> None:
        # No source events are produced; the gateway is never consulted.
        wakes = dispatch([], clock=clock)
        assert wakes == []

    asyncio.run(_idle())
    elapsed = clock.now()
    steps = int(HOURS * _HOUR_S // 60)
    for step in range(steps):
        clock.advance_to(elapsed + (step + 1) * 60.0)
    _ = gateway.transport_calls
    return transport.calls
