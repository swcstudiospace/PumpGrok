"""Four agents run behind the gateway; the signal seat never calls GrokAgent.run."""

import ast
import pathlib

import pytest

from pumpgrok.engine.agents.rug import RugSeat
from pumpgrok.engine.agents.scout import ScoutSeat
from pumpgrok.engine.agents.signal import SignalSeat
from pumpgrok.engine.agents.whale import WhaleSeat
from pumpgrok.grok import GatewayRequest, GrokGateway
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.replay.clock import FixtureClock

REPO = pathlib.Path("src/pumpgrok/engine/agents")


def _gateway() -> GrokGateway:
    async def transport(request: GatewayRequest) -> str:
        return '{"score": 80, "reason": "ok"}'

    return GrokGateway(
        clock=FixtureClock(),
        budget=LayeredBudget(window_cap=100, agent_cap=40, global_cap=200),
        transport=transport,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("seat", [SignalSeat(), ScoutSeat(), WhaleSeat(), RugSeat()])
async def test_seats_run_through_gateway(seat: object) -> None:
    result = await seat.run(  # type: ignore[attr-defined]
        _gateway(), consequence_id="ev-1", prompt_body="candidate", score=90
    )
    assert result is not None
    assert result.parsed["score"] == 80


@pytest.mark.asyncio
async def test_missing_consequence_id_rejected() -> None:
    with pytest.raises(ValueError):
        await SignalSeat().run(_gateway(), consequence_id="", prompt_body="x", score=90)


@pytest.mark.parametrize("name", ["signal.py", "scout.py", "whale.py", "rug.py"])
def test_no_agent_file_calls_grok_agent_run(name: str) -> None:
    tree = ast.parse((REPO / name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in ("GrokAgent", "grok_agent")
        ):
            assert node.attr != "run", name
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "agents.base" not in node.module
    source = (REPO / name).read_text(encoding="utf-8")
    assert "agents.base" not in source
    assert "GrokAgent(" not in source
