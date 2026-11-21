"""Hung Grok transport cannot delay an ExitTrigger sell (EVT-12)."""

import asyncio

import pytest

from pumpgrok.events.models import Event, EventKind
from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.wake import dispatch


@pytest.mark.asyncio
async def test_hung_transport_does_not_delay_exit_sell() -> None:
    clock = FixtureClock()

    async def hung(request: GatewayRequest) -> str:
        await asyncio.sleep(3600)
        return '{"ok": 1}'

    gateway = GrokGateway(
        clock=clock,
        budget=LayeredBudget(window_cap=100, agent_cap=40, global_cap=200),
        transport=hung,
    )
    exit_event = Event(
        kind=EventKind.exit_signal,
        entity_id="pos-1",
        payload={"v": 1},
        occurred_at="2026-01-01T00:00:00.000000Z",
    )
    wakes = dispatch([exit_event], clock=clock)
    assert [wake.seat for wake in wakes] == ["bot-06-exit"]

    request = GatewayRequest(
        agent="signal", prompt="x", consequence_id="c-hung", score=90
    )
    task = asyncio.ensure_future(gateway.call(request))
    # The exit lane proceeds immediately; the hung Grok call never delays it.
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wakes[0].seat == "bot-06-exit"
