<<<<<<< HEAD
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
=======
"""Deterministic prefilter and the single admission path (GRK-01, GRK-06).

A candidate the prefilter rejects spends nothing and never reaches the
transport. An admitted request runs sanitize, cache, coalescing, breaker,
persisted budget and transport, in that order.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import (
    BREAKER_COOLDOWN_S,
    MARKET_WINDOW_S,
    MAX_AGE_S,
    MIN_AGE_S,
    MIN_PRERANK,
    MIN_UNIQUE_BUYERS,
    MINT_COOLDOWN_S,
    Candidate,
    GrokGateway,
    GrokRequest,
    prefilter,
    sanitize,
)
from pumpgrok.replay.clock import FixtureClock

START = 1_800_000_000.0
PROMPT_SHA = "b" * 64


def candidate(now: float = START, **overrides: Any) -> Candidate:
    base: dict[str, Any] = {
        "mint": "MINT1",
        "created_at": now - 600,
        "first_trade_at": now - 300,
        "unique_buyers": 9,
        "prerank": Decimal("0.8"),
        "last_decision_at": None,
    }
    base.update(overrides)
    return Candidate(**base)


class FakeTransport:
    def __init__(self, *, response: str = '{"verdict":"ok"}', error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[str, str]] = []
        self.gate: asyncio.Event | None = None

    async def __call__(self, request: GrokRequest, text: str) -> str:
        self.calls.append((request.event_id, text))
        if self.gate is not None:
            await self.gate.wait()
        if self.error is not None:
            raise self.error
        return self.response


def request(
    *,
    event_id: str = "ev-1",
    agent: str = "narrative",
    text: str = "launch thread",
    cand: Candidate | None = None,
) -> GrokRequest:
    return GrokRequest(
        event_id=event_id,
        agent=agent,
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text=text,
        candidate=cand if cand is not None else candidate(),
    )


def make_gateway(
    tmp_path: Path,
    clock: FixtureClock,
    transport: FakeTransport,
    budget_dir: Path | None = None,
) -> tuple[GrokGateway, LayeredBudget, ResponseCache]:
    budget = LayeredBudget((budget_dir or tmp_path) / "budget.sqlite", clock)
    cache = ResponseCache(tmp_path / "cache.sqlite", clock)
    gateway = GrokGateway(clock=clock, transport=transport, cache=cache, budget=budget)
    return gateway, budget, cache


# ---------------------------------------------------------------- prefilter rules


def test_thresholds_are_the_design_a_values() -> None:
    assert MIN_AGE_S == 120
    assert MAX_AGE_S == 3600
    assert MIN_UNIQUE_BUYERS == 5
    assert MARKET_WINDOW_S == 3600
    assert MINT_COOLDOWN_S == 300
    assert Decimal("0.5") == MIN_PRERANK
    assert BREAKER_COOLDOWN_S == 60


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"created_at": START - 119}, "too_young"),
        ({"created_at": START + 5}, "too_young"),
        ({"created_at": START - 3601}, "too_old"),
        ({"first_trade_at": START - 3601}, "market_window_closed"),
        ({"last_decision_at": START - 299}, "mint_cooldown"),
        ({"unique_buyers": 4}, "too_few_buyers"),
        ({"prerank": Decimal("0.49")}, "low_prerank"),
        ({"prerank": Decimal("1.01")}, "prerank_out_of_range"),
    ],
)
def test_each_rule_rejects_with_its_reason(overrides: dict[str, Any], reason: str) -> None:
    verdict = prefilter(candidate(**overrides), now=START)
    assert verdict.admit is False
    assert verdict.reason == reason


def test_boundaries_admit() -> None:
    assert prefilter(candidate(created_at=START - MIN_AGE_S), now=START).admit
    assert prefilter(candidate(created_at=START - MAX_AGE_S), now=START).admit
    assert prefilter(candidate(first_trade_at=START - MARKET_WINDOW_S), now=START).admit
    assert prefilter(candidate(last_decision_at=START - MINT_COOLDOWN_S), now=START).admit
    assert prefilter(candidate(unique_buyers=MIN_UNIQUE_BUYERS), now=START).admit
    assert prefilter(candidate(prerank=Decimal("0.5")), now=START).admit
    assert prefilter(candidate(prerank=Decimal("1")), now=START).admit


def test_eligible_candidate_is_admitted_with_reason() -> None:
    verdict = prefilter(candidate(), now=START)
    assert verdict.admit is True
    assert verdict.reason == "admitted"


def test_verdict_is_deterministic_for_the_same_inputs() -> None:
    cand = candidate(unique_buyers=2)
    assert prefilter(cand, now=START) == prefilter(cand, now=START)


def test_sanitize_drops_controls_and_format_chars_and_keeps_newlines() -> None:
    assert sanitize("a\u200bb\x00c\x07\n\td") == "abc\n\td"
    assert sanitize("\uff21\uff22") == "AB"


# ---------------------------------------------------------- request validation


def test_event_causation_is_required() -> None:
    with pytest.raises(ValueError):
        request(event_id="")


def test_unknown_agent_is_refused() -> None:
    with pytest.raises(ValueError):
        request(agent="oracle")


# ------------------------------------------------------------- admission path


async def test_noncandidate_spends_nothing_and_calls_no_transport(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    gateway, budget, cache = make_gateway(tmp_path, clock, transport)

    outcome = await gateway.admit(request(cand=candidate(unique_buyers=1)))

    assert outcome.status == "prefilter_skip"
    assert outcome.reason == "too_few_buyers"
    assert outcome.response is None
    assert transport.calls == []
    assert budget.usage() == {"minute": 0, "hour": 0, "day": 0}
    assert cache.count() == 0


async def test_eligible_event_calls_transport_once_then_cache_serves_repeat(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    gateway, budget, _ = make_gateway(tmp_path, clock, transport)

    first = await gateway.admit(request(event_id="ev-1"))
    second = await gateway.admit(request(event_id="ev-2"))

    assert first.status == "fresh"
    assert first.response == '{"verdict":"ok"}'
    assert first.event_id == "ev-1"
    assert second.status == "cache_hit"
    assert second.response == '{"verdict":"ok"}'
    assert second.event_id == "ev-2"
    assert transport.calls == [("ev-1", "launch thread")]
    assert budget.usage()["minute"] == 1


async def test_transport_receives_sanitized_text(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    gateway, _, _ = make_gateway(tmp_path, clock, transport)

    await gateway.admit(request(text="ab\x07cd"))

    assert transport.calls == [("ev-1", "abcd")]


async def test_denied_budget_makes_no_transport_call_and_caches_nothing(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    gateway, _, cache = make_gateway(tmp_path, clock, transport)

    for index in range(4):  # narrative ordinary minute cap is 4
        await gateway.admit(request(event_id=f"ok-{index}", text=f"text {index}"))
    denied = await gateway.admit(request(event_id="late", text="text late"))

    assert denied.status == "rule_fallback"
    assert denied.reason == "budget_exhausted"
    assert denied.response is None
    assert len(transport.calls) == 4
    assert cache.count() == 4  # only the four successful calls are cached


async def test_unavailable_budget_refuses_transport(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    budget_dir = tmp_path / "gone"
    budget_dir.mkdir()
    gateway, _, _ = make_gateway(tmp_path, clock, transport, budget_dir=budget_dir)
    for leftover in budget_dir.iterdir():
        leftover.unlink()
    budget_dir.rmdir()

    outcome = await gateway.admit(request())

    assert outcome.status == "rule_fallback"
    assert outcome.reason == "budget_unavailable"
    assert transport.calls == []


async def test_transport_error_is_negative_cached_not_cached_as_success(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport(error=RuntimeError("boom"))
    gateway, _, _ = make_gateway(tmp_path, clock, transport)

    first = await gateway.admit(request(event_id="ev-1"))
    second = await gateway.admit(request(event_id="ev-2"))

    assert first.status == "rule_fallback"
    assert first.reason == "transport_error"
    assert second.status == "rule_fallback"
    assert second.reason == "cached_transport_error"
    assert len(transport.calls) == 1


# -------------------------------------------------------- breaker and ladder


async def test_breaker_opens_after_three_consecutive_failures_and_probes_once(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport(error=RuntimeError("down"))
    gateway, budget, _ = make_gateway(tmp_path, clock, transport)

    for index in range(3):  # checker has the full minute cap of 6
        outcome = await gateway.admit(request(agent="checker", text=f"fail {index}"))
        assert outcome.reason == "transport_error"
    assert gateway.llm_available is False

    tripped = await gateway.admit(request(agent="checker", text="while open"))
    assert tripped.reason == "breaker_open"
    assert len(transport.calls) == 3

    clock.advance_to(START + BREAKER_COOLDOWN_S)
    transport.error = None
    gate = asyncio.Event()
    transport.gate = gate
    probe = asyncio.create_task(gateway.admit(request(agent="checker", text="probe")))
    for _ in range(5):
        await asyncio.sleep(0)

    second_probe = await gateway.admit(request(agent="checker", text="second probe"))
    assert second_probe.reason == "breaker_open"

    gate.set()
    probed = await probe
    assert probed.status == "fresh"
    assert gateway.llm_available is True
    # three failures and one probe are charged in one hour; refused calls spend nothing
    assert budget.usage()["hour"] == 4


async def test_failed_half_open_probe_reopens_the_breaker(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport(error=RuntimeError("down"))
    gateway, _, _ = make_gateway(tmp_path, clock, transport)
    for index in range(3):
        await gateway.admit(request(agent="checker", text=f"fail {index}"))

    clock.advance_to(START + BREAKER_COOLDOWN_S)
    probe = await gateway.admit(request(agent="checker", text="probe"))
    assert probe.reason == "transport_error"

    reopened = await gateway.admit(request(agent="checker", text="after probe"))
    assert reopened.reason == "breaker_open"

    clock.advance_to(START + 2 * BREAKER_COOLDOWN_S)
    transport.error = None
    recovered = await gateway.admit(request(agent="checker", text="recover"))
    assert recovered.status == "fresh"
    assert gateway.llm_available is True


async def test_hung_transport_hits_the_call_deadline(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = FakeTransport()
    transport.gate = asyncio.Event()  # never set: the transport hangs
    gateway, _, _ = make_gateway(tmp_path, clock, transport)

    task = asyncio.create_task(gateway.admit(request()))
    for _ in range(5):
        await asyncio.sleep(0)
    clock.advance_to(START + 20)
    outcome = await asyncio.wait_for(task, timeout=5)

    assert outcome.status == "rule_fallback"
    assert outcome.reason == "timeout"
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
