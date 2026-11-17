"""Regression: a call queued for an in-flight slot honours the breaker and the deadline.

The gateway admits a call, then waits for one of ``MAX_INFLIGHT`` slots. The
breaker may open while the call waits, and the wait itself may outlast the
call deadline. Neither may let the queued call reach the transport.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest

from pumpgrok.grok import gateway as gateway_module
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import (
    BREAKER_FAILURES,
    TRANSPORT_DEADLINE_S,
    Candidate,
    GrokGateway,
    GrokOutcome,
    GrokRequest,
)
from pumpgrok.replay.clock import FixtureClock

START = 1_800_000_000.0
PROMPT_SHA = "f" * 64


def candidate() -> Candidate:
    return Candidate(
        mint="MINT1",
        created_at=START - 600,
        first_trade_at=START - 300,
        unique_buyers=9,
        prerank=Decimal("0.8"),
        last_decision_at=None,
    )


def request(event_id: str, text: str) -> GrokRequest:
    return GrokRequest(
        event_id=event_id,
        agent="narrative",
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text=text,
        candidate=candidate(),
    )


class ScriptedTransport:
    """``HOLD`` blocks until released; ``FAIL-*`` and ``HOLD`` raise; anything else answers."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.holding = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, req: GrokRequest, _text: str) -> str:
        self.calls.append(req.event_id)
        if req.event_id == "HOLD":
            self.holding.set()
            await self.release.wait()
            raise RuntimeError("upstream down")
        if req.event_id.startswith("FAIL-"):
            raise RuntimeError("upstream down")
        return '{"verdict":"ok"}'


async def settle(rounds: int = 10) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


def make(
    tmp_path: Path, clock: FixtureClock, transport: ScriptedTransport
) -> tuple[GrokGateway, LayeredBudget]:
    budget = LayeredBudget(tmp_path / "budget.sqlite", clock)
    cache = ResponseCache(tmp_path / "cache.sqlite", clock)
    return GrokGateway(clock=clock, transport=transport, cache=cache, budget=budget), budget


async def test_call_queued_while_breaker_opens_is_refused_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway_module, "MAX_INFLIGHT", 1)
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway, budget = make(tmp_path, clock, transport)

    hold = asyncio.create_task(gateway.admit(request("HOLD", "hold")))
    await transport.holding.wait()
    # Each of these passes the closed breaker and queues behind HOLD, in this order.
    fail_1 = asyncio.create_task(gateway.admit(request("FAIL-1", "f1")))
    fail_2 = asyncio.create_task(gateway.admit(request("FAIL-2", "f2")))
    queued = asyncio.create_task(gateway.admit(request("QUEUED", "q")))
    await settle()

    transport.release.set()
    outcomes: list[GrokOutcome] = await asyncio.gather(hold, fail_1, fail_2, queued)

    assert [o.reason for o in outcomes] == [
        "transport_error",
        "transport_error",
        "transport_error",
        "breaker_open",
    ]
    assert outcomes[-1].response is None
    assert transport.calls == ["HOLD", "FAIL-1", "FAIL-2"]
    assert gateway.llm_available is False
    assert budget.usage()["minute"] == 3  # the refused queued call spent nothing


async def test_call_queued_past_its_deadline_never_reaches_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway_module, "MAX_INFLIGHT", 1)
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway, budget = make(tmp_path, clock, transport)

    hold = asyncio.create_task(gateway.admit(request("HOLD", "hold")))
    await transport.holding.wait()
    queued = asyncio.create_task(gateway.admit(request("QUEUED", "q")))
    await settle()

    # The deadline started when QUEUED was admitted, so it fires during the queue wait.
    clock.advance_to(START + TRANSPORT_DEADLINE_S + 1)
    await settle()
    transport.release.set()
    outcomes: list[GrokOutcome] = await asyncio.gather(hold, queued)

    assert outcomes[1].reason == "timeout"
    assert outcomes[1].response is None
    assert "QUEUED" not in transport.calls
    assert budget.usage()["minute"] == 1  # only HOLD was admitted to the transport


async def test_calls_timed_out_in_slot_queue_do_not_count_as_breaker_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gateway_module, "MAX_INFLIGHT", 1)
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway, budget = make(tmp_path, clock, transport)

    hold = asyncio.create_task(gateway.admit(request("HOLD", "hold")))
    await transport.holding.wait()
    # One more queued call than the breaker tolerates: if queued timeouts counted
    # as failures, the breaker would be open after this test's advance.
    queued = [
        asyncio.create_task(gateway.admit(request(f"QUEUED-{i}", f"q{i}")))
        for i in range(BREAKER_FAILURES + 1)
    ]
    await settle()

    # HOLD reached the transport and is cancelled by its deadline. Each queued call
    # is cancelled by the same deadline while still waiting for the slot.
    clock.advance_to(START + TRANSPORT_DEADLINE_S + 1)
    await settle()
    outcomes: list[GrokOutcome] = await asyncio.gather(hold, *queued)

    assert [o.reason for o in outcomes] == ["timeout"] * (1 + len(queued))
    assert all(o.response is None for o in outcomes)
    assert transport.calls == ["HOLD"]
    assert budget.usage()["minute"] == 1  # only HOLD was charged

    # Only HOLD's timeout is a breaker failure: the breaker is still closed.
    assert gateway.llm_available is True
    # Two transport failures more reach the threshold only if HOLD counted exactly once.
    await gateway.admit(request("FAIL-1", "f1"))
    assert gateway.llm_available is True
    await gateway.admit(request("FAIL-2", "f2"))
    assert gateway.llm_available is False
    assert budget.usage()["minute"] == 3
