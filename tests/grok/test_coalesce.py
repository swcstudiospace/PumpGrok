"""In-flight coalescing and the bounded in-flight count (GRK-03)."""

from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest
from pumpgrok.replay.clock import FixtureClock

START = 1_800_000_000.0
PROMPT_SHA = "e" * 64


def candidate() -> Candidate:
    return Candidate(
        mint="MINT1",
        created_at=START - 600,
        first_trade_at=START - 300,
        unique_buyers=9,
        prerank=Decimal("0.8"),
        last_decision_at=None,
    )


def request(event_id: str, *, agent: str = "narrative", text: str = "same") -> GrokRequest:
    return GrokRequest(
        event_id=event_id,
        agent=agent,
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text=text,
        candidate=candidate(),
    )


class GatedTransport:
    def __init__(self) -> None:
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.gate = asyncio.Event()
        self.error: Exception | None = None

    async def __call__(self, _request: GrokRequest, _text: str) -> str:
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await self.gate.wait()
        finally:
            self.active -= 1
        if self.error is not None:
            raise self.error
        return '{"verdict":"ok"}'


def make(
    tmp_path: Path, clock: FixtureClock, transport: GatedTransport
) -> tuple[GrokGateway, LayeredBudget]:
    budget = LayeredBudget(tmp_path / "budget.sqlite", clock)
    cache = ResponseCache(tmp_path / "cache.sqlite", clock)
    return GrokGateway(clock=clock, transport=transport, cache=cache, budget=budget), budget


async def settle(rounds: int = 10) -> None:
    for _ in range(rounds):
        await asyncio.sleep(0)


async def test_hundred_identical_concurrent_requests_make_one_call_and_one_charge(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    gateway, budget = make(tmp_path, clock, transport)

    tasks = [asyncio.create_task(gateway.admit(request(f"ev-{i}"))) for i in range(100)]
    await settle()
    transport.gate.set()
    outcomes: list[Any] = await asyncio.gather(*tasks)

    assert transport.calls == 1
    assert budget.usage()["minute"] == 1
    fresh = [o for o in outcomes if o.status == "fresh"]
    coalesced = [o for o in outcomes if o.status == "coalesced"]
    assert len(fresh) == 1
    assert len(coalesced) == 99
    assert {o.response for o in outcomes} == {'{"verdict":"ok"}'}
    assert [o.event_id for o in outcomes] == [f"ev-{i}" for i in range(100)]


async def test_different_keys_stay_isolated(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    transport.gate.set()
    gateway, budget = make(tmp_path, clock, transport)

    first = await gateway.admit(request("ev-a", text="alpha"))
    second = await gateway.admit(request("ev-b", text="beta"))

    assert transport.calls == 2
    assert budget.usage()["minute"] == 2
    assert first.status == "fresh"
    assert second.status == "fresh"


async def test_in_flight_calls_never_exceed_four(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    gateway, _ = make(tmp_path, clock, transport)

    tasks = [
        asyncio.create_task(gateway.admit(request(f"ev-{i}", agent="checker", text=f"t{i}")))
        for i in range(6)  # six distinct keys; checker may use the full minute of six
    ]
    await settle()
    assert transport.active == 4
    transport.gate.set()
    outcomes = await asyncio.gather(*tasks)

    assert transport.max_active == 4
    assert transport.calls == 6
    assert all(o.status == "fresh" for o in outcomes)


async def test_owner_cancellation_releases_the_key_and_waiters_get_a_fallback(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    gateway, _ = make(tmp_path, clock, transport)

    owner = asyncio.create_task(gateway.admit(request("owner")))
    await settle()
    waiter = asyncio.create_task(gateway.admit(request("waiter")))
    await settle()
    owner.cancel()
    waiter_outcome = await waiter

    assert waiter_outcome.status == "rule_fallback"
    assert waiter_outcome.reason == "cancelled"
    assert waiter_outcome.event_id == "waiter"
    with contextlib.suppress(asyncio.CancelledError):
        await owner

    transport.gate.set()
    retry = await gateway.admit(request("retry"))
    assert retry.status == "fresh"
    assert transport.calls == 2


async def test_cancelled_waiter_does_not_cancel_the_owner(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    gateway, budget = make(tmp_path, clock, transport)

    owner = asyncio.create_task(gateway.admit(request("owner")))
    await settle()
    waiter = asyncio.create_task(gateway.admit(request("waiter")))
    await settle()
    waiter.cancel()
    await settle()

    transport.gate.set()
    outcome = await owner
    assert outcome.status == "fresh"
    assert budget.usage()["minute"] == 1


async def test_failed_call_releases_the_in_flight_entry(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = GatedTransport()
    transport.gate.set()
    transport.error = RuntimeError("down")
    gateway, _ = make(tmp_path, clock, transport)

    failed = await gateway.admit(request("first"))
    assert failed.reason == "transport_error"

    clock.advance_to(START + 30)  # negative entry expires
    transport.error = None
    retried = await gateway.admit(request("second"))
    assert retried.status == "fresh"
    assert transport.calls == 2
