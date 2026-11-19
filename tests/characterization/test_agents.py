"""Characterization: Grok agents and core ops ports (STRUCT-003).

Pins ``engine/agents/*`` against the vendor agents plus ``core/ratelimit.py``,
``core/budget.py`` and ``core/llm.py`` against ``vendor/grokbot-pumpfun/src/ops.py``.
Every x.ai response is served by ``httpx.MockTransport`` behind the real
``XaiTransport`` and ``GrokGateway``, from the hand-authored
``tests/fixtures/http/xai_chat.json`` envelope: no test here reaches the live
network. Time is virtual (an immediate test clock), so cache and budget windows
are deterministic.

Vendor divergences: prompts are English (prompt edits change the canonical
request hash, so the smoke LLM records were authored last); agents reach the
model only through ``GrokGateway.admit``, which owns the prefilter, cache,
breaker and layered budget; the transport makes one attempt per admitted call,
so there is no retry loop and no backoff.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from pumpgrok.config.settings import GrokSettings
from pumpgrok.core.budget import CallBudget
from pumpgrok.core.llm import GrokOps
from pumpgrok.core.ratelimit import RateLimiter
from pumpgrok.engine.agents.auditor import AuditorAgent
from pumpgrok.engine.agents.base import (
    _AGENT_TYPES,
    GrokAgent,
    extract_json,
    result_schemas,
    system_prompts,
)
from pumpgrok.engine.agents.checker import CheckerAgent
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.agents.timing import TimingAgent
from pumpgrok.engine.models import Analysis, Token, TokenMetrics
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway
from pumpgrok.grok.transport import XaiTransport

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "http" / "xai_chat.json"

CHAT_PATH = "/v1/chat/completions"
NOW = 1_767_225_600.0


class ImmediateClock:
    """Virtual time for agent tests: fixed now, sleeps resolve at once."""

    def __init__(self, now: float = NOW) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def set_now(self, now: float) -> None:
        self._now = now

    def monotonic(self) -> float:
        return self._now

    def utc_iso(self) -> str:
        return "2026-01-01T00:00:00.000000Z"

    async def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        return None

    def timeout(self, seconds: float) -> AbstractAsyncContextManager[None]:
        @asynccontextmanager
        async def _scope() -> AsyncIterator[None]:
            yield

        return _scope()


def _grok() -> GrokSettings:
    return GrokSettings(api_key=SecretStr("test-key"))


def _chat_envelope(content: object, model: str = "grok-4.20-0309-non-reasoning") -> dict[str, Any]:
    return {
        "id": "chatcmpl-test-001",
        "object": "chat.completion",
        "created": 1767225600,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(content)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _client(
    handler: Callable[[httpx.Request], httpx.Response], seen: list[httpx.Request]
) -> httpx.AsyncClient:
    def _wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(_wrapped))


def _ok(content: object) -> Callable[[httpx.Request], httpx.Response]:
    def _handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.x.ai"
        assert request.url.path == CHAT_PATH
        return httpx.Response(200, json=_chat_envelope(content))

    return _handle


def _candidate(now: float) -> Candidate:
    """Facts that pass every prefilter rule for a token created five minutes before ``now``."""
    return Candidate(
        mint="M",
        created_at=now - 300.0,
        first_trade_at=now - 60.0,
        unique_buyers=10,
        prerank=Decimal("0.8"),
        last_decision_at=None,
    )


def _admit(now: float = NOW) -> dict[str, Any]:
    """Gateway admission arguments for one agent call at ``now``."""
    return {"event_id": "EV-TEST", "candidate": _candidate(now)}


def _at(clock: ImmediateClock, now: float) -> dict[str, Any]:
    """Move the test clock to ``now`` and return admission arguments for that instant."""
    clock.set_now(now)
    return _admit(now)


def _gateway(tmp_path: Path, clock: ImmediateClock, client: httpx.AsyncClient) -> GrokGateway:
    grok = _grok()
    transport = XaiTransport(
        api_key=grok.api_key.get_secret_value(),
        base_url=grok.base_url,
        client=client,
        prompts=system_prompts(),
        schemas=result_schemas(),
    )
    return GrokGateway(
        clock=clock,
        transport=transport,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )


def _agents(
    tmp_path: Path,
    seen: list[httpx.Request],
    handler: Callable[[httpx.Request], httpx.Response],
    clock: ImmediateClock | None = None,
) -> tuple[NarrativeAgent, CheckerAgent, TimingAgent, AuditorAgent]:
    owned_clock = clock or ImmediateClock()
    gateway = _gateway(tmp_path, owned_clock, _client(handler, seen))
    kwargs: dict[str, Any] = {"gateway": gateway, "clock": owned_clock}
    narrative = NarrativeAgent(_grok(), **kwargs)
    checker = CheckerAgent(_grok(), **kwargs)
    timing = TimingAgent(_grok(), cache_seconds=900.0, **kwargs)
    auditor = AuditorAgent(_grok(), **kwargs)
    return narrative, checker, timing, auditor


def _analysis(token: Token) -> Analysis:
    return Analysis(token=token, metrics=TokenMetrics(risk_score=2.0))


# --- fixture shape ---------------------------------------------------------


def test_smoke_fixture_is_a_usable_chat_completion() -> None:
    envelope = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert envelope["object"] == "chat.completion"
    content = envelope["choices"][0]["message"]["content"]
    data = extract_json(str(content))
    assert {"trend_fit", "virality", "community_signals", "launch_timing"} <= set(data)
    assert envelope["usage"]["prompt_tokens"] == 120


# --- model selection and endpoint ------------------------------------------


async def test_narrative_uses_fast_model_on_sdk_base_url(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(
        tmp_path,
        seen,
        _ok(
            {
                "trend_fit": 1.0,
                "virality": 1.0,
                "community_signals": 1.0,
                "launch_timing": 1.0,
                "reasoning": "ok",
            }
        ),
    )
    token = Token(mint="M", name="n", image_uri="i")
    result = await narrative.run(token, **_admit())
    assert result.trend_fit == 1.0
    (request,) = seen
    assert str(request.url) == "https://api.x.ai" + CHAT_PATH
    body = json.loads(request.content.decode())
    assert body["model"] == "grok-4.20-0309-non-reasoning"
    assert body["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


async def test_checker_uses_strong_model(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    _, checker, _, _ = _agents(
        tmp_path,
        seen,
        _ok({"approve": False, "reason": "thin", "flags": ["thin"], "confidence": 0.2}),
    )
    result = await checker.run(_analysis(Token(mint="M")), **_admit())
    assert result.approve is False
    (request,) = seen
    body = json.loads(request.content.decode())
    assert body["model"] == "grok-4.3"


async def test_timing_and_auditor_use_fast_model(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    _, _, timing, auditor = _agents(
        tmp_path,
        seen,
        _ok(
            {
                "market_sentiment": 0.5,
                "meme_season": 0.5,
                "volume_level": 0.5,
                "anomalies": [],
                "reasoning": "calm",
            }
        ),
    )
    await timing.get(now=NOW, **_admit())
    models = [json.loads(request.content.decode())["model"] for request in seen]
    assert models == ["grok-4.20-0309-non-reasoning"]
    seen.clear()
    token = Token(mint="M", creator="C", created_timestamp=1_767_225_000.0)
    auditor_seen: list[httpx.Request] = []
    _, _, _, auditor2 = _agents(
        tmp_path,
        auditor_seen,
        _ok(
            {
                "coordinated_buying": False,
                "wash_trading": False,
                "creator_dump_prep": False,
                "bundled_launch": False,
                "organic_buyer_share": 0.9,
                "confidence": 0.8,
                "flags": [],
                "reasoning": "clean",
            }
        ),
    )
    result = await auditor2.run(token, [], [], **_admit())
    assert result.organic_buyer_share == 0.9
    body = json.loads(auditor_seen[0].content.decode())
    assert body["model"] == "grok-4.20-0309-non-reasoning"
    _ = auditor


# --- one attempt, fallback ---------------------------------------------------


async def test_server_error_is_one_attempt_then_falls_back(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(
        tmp_path, seen, lambda request: httpx.Response(500, json={"error": "sick"})
    )
    result = await narrative.run(Token(mint="M"), **_admit())
    assert result.trend_fit == 0.0
    assert len(seen) == 1


async def test_transport_failure_falls_back_pessimistic(tmp_path: Path) -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    seen: list[httpx.Request] = []
    _, checker, _, _ = _agents(tmp_path, seen, _boom)
    result = await checker.run(_analysis(Token(mint="M")), **_admit())
    assert result.approve is False
    assert result.flags == ["agent_failure"]
    assert len(seen) == 1


async def test_bad_json_falls_back_pessimistic(tmp_path: Path) -> None:
    def _prose(request: httpx.Request) -> httpx.Response:
        envelope = _chat_envelope("just some words, no object")
        envelope["choices"][0]["message"]["content"] = "just some words, no object"
        return httpx.Response(200, json=envelope)

    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(tmp_path, seen, _prose)
    result = await narrative.run(Token(mint="M"), **_admit())
    assert result.trend_fit == 0.0


async def test_schema_violation_falls_back_pessimistic(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(tmp_path, seen, _ok({"wrong": "shape"}))
    result = await narrative.run(Token(mint="M"), **_admit())
    assert result.trend_fit == 0.0


async def test_client_error_does_not_retry(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(tmp_path, seen, lambda request: httpx.Response(401, json={}))
    result = await narrative.run(Token(mint="M"), **_admit())
    assert result.trend_fit == 0.0
    assert len(seen) == 1


async def test_prompt_error_falls_back_without_http(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(tmp_path, seen, _ok({}))
    result = await narrative.run(None, **_admit())  # type: ignore[arg-type]
    assert result.trend_fit == 0.0
    assert seen == []


async def test_budget_refusal_falls_back_without_http(tmp_path: Path) -> None:
    clock = ImmediateClock()
    budget = LayeredBudget(tmp_path / "budget.sqlite", clock)
    # Ordinary callers keep the reserve share: a minute holds 6 calls, 4 of them ordinary.
    for _ in range(4):
        assert budget.try_charge(reserve_priority=False) is True
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(tmp_path, seen, _ok({}), clock=clock)
    result = await narrative.run(Token(mint="M"), **_admit())
    assert result.trend_fit == 0.0
    assert result.reasoning == "budget_exhausted"
    assert seen == []


async def test_ops_slot_counts_and_snapshot_reports() -> None:
    clock = ImmediateClock()
    ops = GrokOps(RateLimiter(6000.0, None, clock), CallBudget(10, clock))
    async with ops.slot("narrative"):
        ops.record_success("narrative", {"prompt_tokens": 3, "completion_tokens": 2})
    ops.record_failure("checker")
    snapshot = ops.snapshot()
    assert snapshot["calls"] == {"narrative": 1}
    assert snapshot["tokens_in"] == 3
    assert snapshot["tokens_out"] == 2
    assert snapshot["failures"] == {"checker": 1}
    assert snapshot["budget_spent"] == 0


# --- timing cache -----------------------------------------------------------


async def test_timing_caches_within_window_and_refreshes_after(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    clock = ImmediateClock(now=1_000.0)
    _, _, timing, _ = _agents(
        tmp_path,
        seen,
        _ok(
            {
                "market_sentiment": 0.6,
                "meme_season": 0.6,
                "volume_level": 0.6,
                "anomalies": [],
                "reasoning": "steady",
            }
        ),
        clock=clock,
    )
    first = await timing.get(now=1_000.0, **_at(clock, 1_000.0))
    second = await timing.get(now=1_100.0, **_at(clock, 1_100.0))
    assert second is first
    assert len(seen) == 1
    third = await timing.get(now=1_901.0, **_at(clock, 1_901.0))
    assert third is not first
    assert len(seen) == 2


async def test_timing_failure_is_not_cached(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    clock = ImmediateClock(now=2_000.0)
    _, _, timing, _ = _agents(
        tmp_path, seen, lambda request: httpx.Response(500, json={}), clock=clock
    )
    first = await timing.get(now=2_000.0, **_at(clock, 2_000.0))
    assert first.anomalies == ["agent_failure"]
    second = await timing.get(now=2_001.0, **_at(clock, 2_001.0))
    assert second is not first
    assert len(seen) == 2


async def test_timing_invalidate_forces_refresh(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    clock = ImmediateClock(now=3_000.0)
    _, _, timing, _ = _agents(
        tmp_path,
        seen,
        _ok(
            {
                "market_sentiment": 0.4,
                "meme_season": 0.4,
                "volume_level": 0.4,
                "anomalies": [],
                "reasoning": "soft",
            }
        ),
        clock=clock,
    )
    await timing.get(now=3_000.0, **_at(clock, 3_000.0))
    timing.invalidate()
    await timing.get(now=3_001.0, **_at(clock, 3_001.0))
    assert len(seen) == 2


# --- core limiter behavior --------------------------------------------------


def test_rate_limiter_admits_then_reports_delay() -> None:
    clock = ImmediateClock()
    limiter = RateLimiter(per_minute=60.0, burst=2.0, clock=clock)
    assert limiter.delay_for_next() == 0.0
    limiter.tokens = 0.0
    limiter.updated = clock.monotonic()
    assert limiter.delay_for_next() == pytest.approx(1.0)


async def test_rate_limiter_acquire_spends_token() -> None:
    clock = ImmediateClock()
    limiter = RateLimiter(per_minute=60.0, burst=2.0, clock=clock)
    assert await limiter.acquire() == 0.0
    assert limiter.tokens == pytest.approx(1.0)


def test_budget_spends_and_rolls_at_midnight() -> None:
    clock = ImmediateClock(now=1_767_225_600.0)
    budget = CallBudget(max_per_day=2, clock=clock)
    assert budget.try_spend() is True
    assert budget.try_spend() is True
    assert budget.try_spend() is False
    assert budget.remaining == 0
    clock._now += 86_400.0
    assert budget.remaining == 2
    assert budget.try_spend() is True


def test_extract_json_accepts_fenced_and_bare_objects() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('noise {"a": 3} trailing') == {"a": 3}
    with pytest.raises(ValueError):
        extract_json("no object here")
    with pytest.raises(ValueError):
        extract_json('{"a": 1')


# --- regression: unit, registry and clock contracts -------------------------


_TIMING_OK: dict[str, object] = {
    "market_sentiment": 0.5,
    "meme_season": 0.5,
    "volume_level": 0.5,
    "anomalies": [],
    "reasoning": "calm",
}


def test_narrative_payload_reports_market_cap_in_sol(tmp_path: Path) -> None:
    narrative, _, _, _ = _agents(tmp_path, [], _ok({}))
    token = Token(mint="M", market_cap_sol=35_000_000_000)
    payload = json.loads(narrative.build_user_message(token))
    assert payload["market_cap_sol"] == 35.0


def test_duplicate_agent_name_is_refused_and_first_binding_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Restores the registry at teardown even when the unfixed code rebinds the name.
    monkeypatch.setitem(_AGENT_TYPES, NarrativeAgent.name, NarrativeAgent)
    with pytest.raises(ValueError, match="already bound"):

        class ImpostorNarrative(GrokAgent):
            name = "narrative"

    assert _AGENT_TYPES["narrative"] is NarrativeAgent


async def test_backward_clock_step_refreshes_the_cached_verdict(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    clock = ImmediateClock(now=2_000.0)
    _, _, timing, _ = _agents(tmp_path, seen, _ok(_TIMING_OK), clock=clock)
    await timing.get(now=2_000.0, **_at(clock, 2_000.0))
    await timing.get(now=1_000.0, **_at(clock, 1_000.0))
    assert len(seen) == 2


async def test_concurrent_identical_timing_calls_share_one_gateway_call(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    _, _, timing, _ = _agents(tmp_path, seen, _ok(_TIMING_OK))
    first, second = await asyncio.gather(
        timing.get(now=NOW, **_admit()), timing.get(now=NOW, **_admit())
    )
    assert len(seen) == 1
    assert first.market_sentiment == second.market_sentiment == 0.5
