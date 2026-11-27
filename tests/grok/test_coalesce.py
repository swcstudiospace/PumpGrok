"""N identical concurrent requests make one transport call."""

import asyncio

import pytest

from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.replay.clock import FixtureClock


@pytest.mark.asyncio
async def test_identical_concurrent_requests_share_one_call() -> None:
    clock = FixtureClock()
    budget = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200)
    calls = 0

    async def transport(request: GatewayRequest) -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return '{"ok": 1}'

    gateway = GrokGateway(clock=clock, budget=budget, transport=transport)
    request = GatewayRequest(agent="scout", prompt="hello", consequence_id="c-1", score=90)
    results = await asyncio.gather(*[gateway.call(request) for _ in range(5)])
    assert calls == 1
    assert all(result is not None and result.parsed == {"ok": 1} for result in results)
    assert gateway.transport_calls == 1
