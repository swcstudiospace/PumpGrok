"""Characterization: Grok agents and core ops ports (STRUCT-003).

Pins ``engine/agents/*`` against the vendor agents plus ``core/ratelimit.py``,
``core/budget.py`` and ``core/llm.py`` against ``vendor/grokbot-pumpfun/src/ops.py``.
Every x.ai response is served by ``httpx.MockTransport`` from the
hand-authored ``tests/fixtures/http/xai_chat.json`` envelope: no test here
reaches the live network. Time is virtual (an immediate test clock) and
jitter comes from ``make_rng`` seeds, so retries are deterministic.

Vendor divergences: prompts are English (prompt edits change the canonical
request hash, so the smoke LLM records were authored last); retry and
timeout knobs travel as agent constructor arguments, not settings; the
circuit breaker is Phase 4 per R52, so ``precheck`` reports the budget only.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from random import Random
from typing import Any

import httpx
import pytest

from pumpgrok.config.settings import GrokSettings
from pumpgrok.core.budget import CallBudget
from pumpgrok.core.llm import GrokOps
from pumpgrok.core.ratelimit import RateLimiter
from pumpgrok.engine.agents.auditor import AuditorAgent
from pumpgrok.engine.agents.base import extract_json
from pumpgrok.engine.agents.checker import CheckerAgent
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.agents.timing import TimingAgent
from pumpgrok.engine.models import Analysis, Token, TokenMetrics
from pumpgrok.replay.rng import make_rng

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "http" / "xai_chat.json"

CHAT_PATH = "/v1/chat/completions"


class ImmediateClock:
    """Virtual time for agent tests: fixed now, sleeps resolve at once."""

    def __init__(self, now: float = 1_767_225_600.0) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

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
    return GrokSettings()


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


def _agents(
    seen: list[httpx.Request],
    handler: Callable[[httpx.Request], httpx.Response],
    clock: ImmediateClock | None = None,
    ops: GrokOps | None = None,
    seed: int = 7,
) -> tuple[NarrativeAgent, CheckerAgent, TimingAgent, AuditorAgent]:
    owned_clock = clock or ImmediateClock()
    rng = make_rng(seed)
    client = _client(handler, seen)
    kwargs: dict[str, Any] = {
        "clock": owned_clock,
        "rng": rng,
        "client": client,
        "ops": ops,
    }
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


async def test_narrative_uses_fast_model_on_sdk_base_url() -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(
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
    result = await narrative.run(token)
    assert result.trend_fit == 1.0
    (request,) = seen
    assert str(request.url) == "https://api.x.ai" + CHAT_PATH
    body = json.loads(request.content.decode())
    assert body["model"] == "grok-4.20-0309-non-reasoning"
    assert body["temperature"] == 0
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


async def test_checker_uses_strong_model() -> None:
    seen: list[httpx.Request] = []
    _, checker, _, _ = _agents(
        seen, _ok({"approve": False, "reason": "thin", "flags": ["thin"], "confidence": 0.2})
    )
    result = await checker.run(_analysis(Token(mint="M")))
    assert result.approve is False
    (request,) = seen
    body = json.loads(request.content.decode())
    assert body["model"] == "grok-4.3"


async def test_timing_and_auditor_use_fast_model() -> None:
    seen: list[httpx.Request] = []
    _, _, timing, auditor = _agents(
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
    await timing.get(now=1_767_225_600.0)
    models = [json.loads(request.content.decode())["model"] for request in seen]
    assert models == ["grok-4.20-0309-non-reasoning"]
    seen.clear()
    token = Token(mint="M", creator="C", created_timestamp=1_767_225_000.0)
    auditor_seen: list[httpx.Request] = []
    _, _, _, auditor2 = _agents(
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
    result = await auditor2.run(token, [], [])
    assert result.organic_buyer_share == 0.9
    body = json.loads(auditor_seen[0].content.decode())
    assert body["model"] == "grok-4.20-0309-non-reasoning"
    _ = auditor


# --- retry, backoff, fallback ----------------------------------------------


async def test_retry_then_success_records_usage() -> None:
    seen: list[httpx.Request] = []
    calls = {"n": 0}

    def _flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "sick"})
        return httpx.Response(
            200,
            json=_chat_envelope(
                {
                    "trend_fit": 0.5,
                    "virality": 0.5,
                    "community_signals": 0.5,
                    "launch_timing": 0.5,
                    "reasoning": "recovered",
                }
            ),
        )

    narrative, _, _, _ = _agents(seen, _flaky)
    result = await narrative.run(Token(mint="M"))
    assert result.trend_fit == 0.5
    assert calls["n"] == 2


async def test_backoff_is_seeded_jitter() -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, _ok({}), seed=11)
    expected = 1.0 * (0.5 + Random(11).random())
    assert narrative._backoff(1) == pytest.approx(expected)


async def test_transport_failure_falls_back_pessimistic() -> None:
    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    seen: list[httpx.Request] = []
    _, checker, _, _ = _agents(seen, _boom)
    result = await checker.run(_analysis(Token(mint="M")))
    assert result.approve is False
    assert result.flags == ["agent_failure"]
    assert len(seen) == 3


async def test_bad_json_falls_back_pessimistic() -> None:
    def _prose(request: httpx.Request) -> httpx.Response:
        envelope = _chat_envelope("just some words, no object")
        envelope["choices"][0]["message"]["content"] = "just some words, no object"
        return httpx.Response(200, json=envelope)

    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, _prose)
    result = await narrative.run(Token(mint="M"))
    assert result.trend_fit == 0.0


async def test_schema_violation_falls_back_pessimistic() -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, _ok({"wrong": "shape"}))
    result = await narrative.run(Token(mint="M"))
    assert result.trend_fit == 0.0


async def test_client_error_does_not_retry() -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, lambda request: httpx.Response(401, json={}))
    result = await narrative.run(Token(mint="M"))
    assert result.trend_fit == 0.0
    assert len(seen) == 1


async def test_prompt_error_falls_back_without_http() -> None:
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, _ok({}))
    result = await narrative.run(None)  # type: ignore[arg-type]
    assert result.trend_fit == 0.0
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


async def test_precheck_block_falls_back_without_http() -> None:
    clock = ImmediateClock()
    budget = CallBudget(max_per_day=1, clock=clock)
    assert budget.try_spend() is True
    ops = GrokOps(RateLimiter(600.0, None, clock), budget)
    seen: list[httpx.Request] = []
    narrative, _, _, _ = _agents(seen, _ok({}), clock=clock, ops=ops)
    result = await narrative.run(Token(mint="M"))
    assert result.trend_fit == 0.0
    assert seen == []
    assert ops.snapshot()["blocked"] == {"narrative": 1}


# --- timing cache -----------------------------------------------------------


async def test_timing_caches_within_window_and_refreshes_after() -> None:
    seen: list[httpx.Request] = []
    _, _, timing, _ = _agents(
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
    )
    first = await timing.get(now=1_000.0)
    second = await timing.get(now=1_100.0)
    assert second is first
    assert len(seen) == 1
    third = await timing.get(now=1_901.0)
    assert third is not first
    assert len(seen) == 2


async def test_timing_failure_is_not_cached() -> None:
    seen: list[httpx.Request] = []
    _, _, timing, _ = _agents(seen, lambda request: httpx.Response(500, json={}))
    first = await timing.get(now=2_000.0)
    assert first.anomalies == ["agent_failure"]
    second = await timing.get(now=2_001.0)
    assert second is not first
    assert len(seen) == 6


async def test_timing_invalidate_forces_refresh() -> None:
    seen: list[httpx.Request] = []
    _, _, timing, _ = _agents(
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
    )
    await timing.get(now=3_000.0)
    timing.invalidate()
    await timing.get(now=3_001.0)
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
