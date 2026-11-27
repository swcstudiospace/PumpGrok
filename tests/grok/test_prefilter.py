"""Prefilter admits above threshold; skip spends nothing."""

import pytest

from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.prefilter import Prefilter
from pumpgrok.replay.clock import FixtureClock


def test_prefilter_is_deterministic() -> None:
    prefilter = Prefilter(clock=FixtureClock(), threshold=50)
    assert not prefilter.admits(49)
    assert prefilter.admits(50)
    assert prefilter.admits(100)
    assert prefilter.admits(50) == prefilter.admits(50)


@pytest.mark.asyncio
async def test_prefilter_skip_spends_no_budget() -> None:
    clock = FixtureClock()
    budget = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200)
    called = 0

    async def transport(request: GatewayRequest) -> str:
        nonlocal called
        called += 1
        return '{"ok": 1}'

    gateway = GrokGateway(clock=clock, budget=budget, transport=transport)
    result = await gateway.call(
        GatewayRequest(agent="scout", prompt="x", consequence_id="c-1", score=10)
    )
    assert result is None
    assert called == 0
    assert budget.window_spent == 0
    assert budget.global_spent == 0


@pytest.mark.asyncio
async def test_admitted_candidate_reaches_transport() -> None:
    clock = FixtureClock()
    budget = LayeredBudget(window_cap=100, agent_cap=40, global_cap=200)

    async def transport(request: GatewayRequest) -> str:
        return '{"ok": 1}'

    gateway = GrokGateway(clock=clock, budget=budget, transport=transport)
    result = await gateway.call(
        GatewayRequest(agent="scout", prompt="hello", consequence_id="c-2", score=90)
    )
    assert result is not None
    assert result.parsed == {"ok": 1}
    assert budget.window_spent == 1
