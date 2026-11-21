"""Replay backend returns recorded hashes and raises on a miss, no network."""

import pytest

from pumpgrok.grok import GatewayRequest, GrokGateway, ReplayBackend, ReplayMiss
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.replay.clock import FixtureClock


@pytest.mark.asyncio
async def test_replay_hit_returns_recorded() -> None:
    clock = FixtureClock()
    request = GatewayRequest(agent="scout", prompt="hello", consequence_id="c-1", score=90)
    backend = ReplayBackend(recorded={request.cache_key: '{"ok": 1}'})
    gateway = GrokGateway(
        clock=clock,
        budget=LayeredBudget(window_cap=100, agent_cap=40, global_cap=200),
        transport=backend,
    )
    result = await gateway.call(request)
    assert result is not None
    assert result.parsed == {"ok": 1}


@pytest.mark.asyncio
async def test_replay_miss_raises() -> None:
    clock = FixtureClock()
    request = GatewayRequest(agent="scout", prompt="hello", consequence_id="c-9", score=90)
    backend = ReplayBackend(recorded={})
    gateway = GrokGateway(
        clock=clock,
        budget=LayeredBudget(window_cap=100, agent_cap=40, global_cap=200),
        transport=backend,
    )
    with pytest.raises(ReplayMiss):
        await gateway.call(request)


def test_replay_backend_imports_no_transport_library() -> None:
    import pathlib

    source = pathlib.Path("src/pumpgrok/grok/__init__.py").read_text(encoding="utf-8")
    assert "httpx" not in source
    assert "requests" not in source
