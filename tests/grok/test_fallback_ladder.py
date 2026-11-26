<<<<<<< HEAD
"""Fallback ladder follows signal_scoring_mode; breaker and probe on FixtureClock."""

from pumpgrok.grok.fallback import FallbackLadder
from pumpgrok.replay.clock import FixtureClock


def test_primary_mode_picks_primary() -> None:
    ladder = FallbackLadder(clock=FixtureClock(), signal_scoring_mode="primary")
    assert ladder.next_model("strong", "fast") == "strong"


def test_fast_mode_picks_fast() -> None:
    ladder = FallbackLadder(clock=FixtureClock(), signal_scoring_mode="fast")
    assert ladder.next_model("strong", "fast") == "fast"


def test_breaker_opens_and_probe_readmits() -> None:
    clock = FixtureClock()
    ladder = FallbackLadder(clock=clock, signal_scoring_mode="primary")
    for _ in range(3):
        ladder.record_failure()
    assert ladder.breaker_open
    assert ladder.next_model("strong", "fast") == "deterministic"
    clock.advance_to(61.0)
    assert not ladder.breaker_open
    assert ladder.try_half_open_probe()
    assert not ladder.try_half_open_probe()
    ladder.finish_probe(success=True)
    assert not ladder.breaker_open
    assert ladder.next_model("strong", "fast") == "strong"


def test_probe_failure_reopens_breaker() -> None:
    clock = FixtureClock()
    ladder = FallbackLadder(clock=clock, signal_scoring_mode="primary")
    for _ in range(3):
        ladder.record_failure()
    clock.advance_to(61.0)
    assert ladder.try_half_open_probe()
    ladder.finish_probe(success=False)
    assert ladder.breaker_open


def test_deterministic_result_is_stable() -> None:
    ladder = FallbackLadder(clock=FixtureClock())
    assert ladder.deterministic_result("ev-1") == ladder.deterministic_result("ev-1")
=======
"""Fallback ladder and circuit breaker over the gateway (GRK-06).

The ladder maps gateway outcomes to scoring modes exactly as
``DegradedState.signal_scoring_mode`` does: fresh and cached answers keep the
LLM, a breaker or budget refusal drops to rule fallback, and ``require_llm``
turns that into observe-only buys. The breaker opens after three consecutive
failures, refuses without spend while open, and admits exactly one half-open
probe after the 60 s cooldown on the injected clock.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

from pumpgrok.core.budget import CallBudget
from pumpgrok.core.llm import GrokOps
from pumpgrok.core.ratelimit import RateLimiter
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import BREAKER_COOLDOWN_S, Candidate, GrokGateway, GrokRequest
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.scheduler.degraded import DegradedState

START = 1_800_000_000.0
PROMPT_SHA = "a" * 64
ANSWER = '{"verdict":"ok"}'


def _candidate(prerank: str = "0.8") -> Candidate:
    return Candidate(
        mint="MINT1",
        created_at=START - 600,
        first_trade_at=START - 300,
        unique_buyers=9,
        prerank=Decimal(prerank),
        last_decision_at=None,
    )


def _request(text: str, *, event_id: str | None = None, prerank: str = "0.8") -> GrokRequest:
    return GrokRequest(
        event_id=event_id or f"ev-{text}",
        agent="narrative",
        model="grok-test",
        prompt_sha=PROMPT_SHA,
        schema="verdict.v1",
        input={"mint": "MINT1"},
        text=text,
        candidate=_candidate(prerank),
    )


class ScriptedTransport:
    """Pops one scripted outcome per call; an exception is raised, a string is returned."""

    def __init__(self) -> None:
        self.calls = 0
        self.script: list[str | BaseException] = []
        self.gate: asyncio.Event | None = None

    async def __call__(self, _request: GrokRequest, _text: str) -> str:
        self.calls += 1
        if self.gate is not None:
            await self.gate.wait()
        item = self.script.pop(0) if self.script else ANSWER
        if isinstance(item, BaseException):
            raise item
        return item


def _gateway(tmp_path: Path, clock: FixtureClock, transport: ScriptedTransport) -> GrokGateway:
    return GrokGateway(
        clock=clock,
        transport=transport,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )


def _mode(gateway: GrokGateway, degraded: DegradedState) -> str:
    degraded.llm_available = gateway.llm_available
    return degraded.signal_scoring_mode(replay=False)


async def _settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


async def test_ladder_steps_map_to_scoring_modes(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)
    degraded = DegradedState()

    fresh = await gateway.admit(_request("market-a"))
    cached = await gateway.admit(_request("market-a", event_id="ev-again"))
    skipped = await gateway.admit(_request("market-b", prerank="0.1"))

    assert fresh.status == "fresh"
    assert cached.status == "cache_hit"
    assert skipped.status == "prefilter_skip"
    assert transport.calls == 1
    assert _mode(gateway, degraded) == "llm"


async def test_two_failures_keep_the_breaker_closed_three_open_it(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)
    degraded = DegradedState()
    transport.script = [RuntimeError("503"), RuntimeError("503")]

    first = await gateway.admit(_request("a"))
    second = await gateway.admit(_request("b"))

    assert (first.reason, second.reason) == ("transport_error", "transport_error")
    assert gateway.llm_available is True
    assert _mode(gateway, degraded) == "llm"

    transport.script = [RuntimeError("503")]
    third = await gateway.admit(_request("c"))

    assert third.status == "rule_fallback"
    assert third.reason == "transport_error"
    assert gateway.llm_available is False
    assert _mode(gateway, degraded) == "rule_fallback"
    degraded.require_llm = True
    assert _mode(gateway, degraded) == "observe_only_buys"


async def test_open_breaker_refuses_without_a_call_or_spend(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)
    transport.script = [RuntimeError("down")] * 3
    for index in range(3):
        await gateway.admit(_request(f"fail-{index}"))
    budget = LayeredBudget(tmp_path / "budget.sqlite", clock)
    usage_before = budget.usage()
    calls_before = transport.calls

    outcome = await gateway.admit(_request("refused"))

    assert outcome.status == "rule_fallback"
    assert outcome.reason == "breaker_open"
    assert transport.calls == calls_before
    assert budget.usage() == usage_before


async def test_half_open_admits_one_probe_and_success_closes(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)
    degraded = DegradedState()
    transport.script = [RuntimeError("down")] * 3
    for index in range(3):
        await gateway.admit(_request(f"fail-{index}"))
    assert _mode(gateway, degraded) == "rule_fallback"

    clock.advance_to(START + BREAKER_COOLDOWN_S - 1)
    early = await gateway.admit(_request("too-early"))
    assert early.reason == "breaker_open"

    transport.gate = asyncio.Event()
    clock.advance_to(START + BREAKER_COOLDOWN_S)
    probe = asyncio.create_task(gateway.admit(_request("probe")))
    await _settle()
    concurrent = await gateway.admit(_request("second-during-probe"))

    assert concurrent.reason == "breaker_open"
    assert transport.calls == 4, "only the probe reaches the transport"

    transport.gate.set()
    outcome = await probe

    assert outcome.status == "fresh"
    assert gateway.llm_available is True
    assert _mode(gateway, degraded) == "llm"


async def test_failed_probe_reopens_with_a_fresh_cooldown(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)
    transport.script = [RuntimeError("down")] * 4
    for index in range(3):
        await gateway.admit(_request(f"fail-{index}"))

    clock.advance_to(START + BREAKER_COOLDOWN_S)
    probe = await gateway.admit(_request("probe"))
    assert probe.reason == "transport_error"
    assert gateway.llm_available is False

    clock.advance_to(START + 2 * BREAKER_COOLDOWN_S - 1)
    assert (await gateway.admit(_request("still-open"))).reason == "breaker_open"

    clock.advance_to(START + 2 * BREAKER_COOLDOWN_S)
    assert (await gateway.admit(_request("second-probe"))).status == "fresh"
    assert gateway.llm_available is True


async def test_budget_refusal_is_a_fallback_that_never_opens_the_breaker(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    transport = ScriptedTransport()
    gateway = _gateway(tmp_path, clock, transport)

    reasons = []
    for index in range(12):
        outcome = await gateway.admit(_request(f"spend-{index}"))
        reasons.append(outcome.reason)
        if outcome.reason == "budget_exhausted":
            break

    assert "budget_exhausted" in reasons
    assert gateway.llm_available is True


async def test_gateway_call_counts_without_spending_the_call_budget() -> None:
    clock = FixtureClock(start=START)
    ops = GrokOps(RateLimiter(60.0, 10.0, clock), CallBudget(2, clock))

    ops.gateway_call("narrative", {"prompt_tokens": 3, "completion_tokens": 4})

    assert ops.calls["narrative"] == 1
    assert ops.tokens_in == 3
    assert ops.tokens_out == 4
    assert ops.budget.remaining == 2
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
