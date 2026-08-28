"""Агенты с замоканным HTTP. В сеть тесты не ходят: весь транспорт — это
httpx.MockTransport.

Главное, что здесь проверяется, — пессимистичный фолбэк. Кривой JSON,
таймаут, пятисотка, ответ не по схеме: во всех случаях агент обязан вернуть
худший вариант, а не пустой и не нейтральный.
"""

import json

import httpx
import pytest

from src.agents import AuditorAgent, CheckerAgent, NarrativeAgent, TimingAgent
from src.agents.base import GrokAgent, extract_json
from src.models import (
    Analysis,
    AuditResult,
    CheckerResult,
    Config,
    NarrativeResult,
    TimingResult,
    Token,
    TokenMetrics,
    Trade,
)


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.grok.api_key = "test-key"
    cfg.grok.max_retries = 3
    cfg.grok.retry_base_delay = 0.0      # тесты не должны ждать ретраи
    cfg.scoring.timing_cache_seconds = 900.0
    return cfg


def grok_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def client_returning(content: str, calls: list | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(json.loads(request.content))
        return grok_response(content)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def client_raising(exc: Exception, calls: list | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        raise exc

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def token() -> Token:
    return Token(mint="Mint1", name="Cat", symbol="CAT", image_uri="https://i", creator="C")


# --- аудитор --------------------------------------------------------------


AUDIT_OK = json.dumps(
    {
        "coordinated_buying": False,
        "wash_trading": False,
        "creator_dump_prep": False,
        "bundled_launch": False,
        "organic_buyer_share": 0.82,
        "confidence": 0.7,
        "flags": [],
        "reasoning": "покупки разрозненные",
    }
)


async def test_auditor_parses_valid_json(config):
    calls: list = []
    async with AuditorAgent(config, client_returning(AUDIT_OK, calls)) as agent:
        result = await agent.run(token(), [], [], TokenMetrics())
    assert isinstance(result, AuditResult)
    assert result.organic_buyer_share == 0.82
    assert result.score == pytest.approx(0.82)
    assert calls[0]["temperature"] == 0
    assert calls[0]["model"] == config.grok.fast_model


async def test_auditor_sends_trades_in_prompt(config):
    calls: list = []
    trades = [Trade(wallet="w1", sol_amount=0.5, timestamp=100.0)]
    async with AuditorAgent(config, client_returning(AUDIT_OK, calls)) as agent:
        await agent.run(token(), trades, [], TokenMetrics())
    user_message = calls[0]["messages"][1]["content"]
    assert "w1" in user_message


async def test_auditor_broken_json_is_pessimistic(config):
    async with AuditorAgent(config, client_returning("почти JSON, но нет {")) as agent:
        result = await agent.run(token(), [], [], TokenMetrics())
    assert result.coordinated_buying
    assert result.wash_trading
    assert result.creator_dump_prep
    assert result.bundled_launch
    assert result.organic_buyer_share == 0.0
    assert result.confidence == 0.0
    assert result.score == 0.0
    assert "agent_failure" in result.flags


async def test_auditor_handles_markdown_fence(config):
    fenced = f"```json\n{AUDIT_OK}\n```"
    async with AuditorAgent(config, client_returning(fenced)) as agent:
        result = await agent.run(token(), [], [], TokenMetrics())
    assert result.organic_buyer_share == 0.82


async def test_auditor_timeout_is_pessimistic(config):
    calls: list = []
    client = client_raising(httpx.ReadTimeout("timeout"), calls)
    async with AuditorAgent(config, client) as agent:
        result = await agent.run(token(), [], [], TokenMetrics())
    assert result.score == 0.0
    assert len(calls) == config.grok.max_retries     # ретраи отработали


async def test_schema_mismatch_is_pessimistic(config):
    bad = json.dumps({"organic_buyer_share": "почти вся", "confidence": 0.9})
    async with AuditorAgent(config, client_returning(bad)) as agent:
        result = await agent.run(token(), [], [], TokenMetrics())
    assert "agent_failure" in result.flags
    assert result.score == 0.0


# --- нарратив -------------------------------------------------------------


async def test_narrative_parses_and_averages(config):
    body = json.dumps(
        {"trend_fit": 0.8, "virality": 0.6, "community_signals": 0.4,
         "launch_timing": 0.2, "reasoning": "ок"}
    )
    async with NarrativeAgent(config, client_returning(body)) as agent:
        result = await agent.run(token())
    assert isinstance(result, NarrativeResult)
    assert result.score == pytest.approx(0.5)


async def test_narrative_empty_response_is_zero(config):
    async with NarrativeAgent(config, client_returning("")) as agent:
        result = await agent.run(token())
    assert result.score == 0.0


# --- тайминг и кэш --------------------------------------------------------


TIMING_OK = json.dumps(
    {"market_sentiment": 0.7, "meme_season": 0.8, "volume_level": 0.6,
     "anomalies": [], "reasoning": "фон обычный"}
)


async def test_timing_caches_result(config):
    calls: list = []
    async with TimingAgent(config, client_returning(TIMING_OK, calls)) as agent:
        first = await agent.get({"x": 1})
        second = await agent.get({"x": 1})
    assert len(calls) == 1                    # второй раз в сеть не пошли
    assert second is first
    assert first.score == pytest.approx(0.7)


async def test_timing_cache_expires(config):
    config.scoring.timing_cache_seconds = 0.0
    calls: list = []
    async with TimingAgent(config, client_returning(TIMING_OK, calls)) as agent:
        await agent.get()
        await agent.get()
    assert len(calls) == 2


async def test_timing_failure_is_not_cached(config):
    """Сбой не должен блокировать оценку рынка на все 15 минут."""
    calls: list = []
    async with TimingAgent(config, client_raising(httpx.ConnectError("нет сети"), calls)) as agent:
        first = await agent.get()
        assert "agent_failure" in first.anomalies
        assert agent._cached is None
        await agent.get()
    assert len(calls) == 2 * config.grok.max_retries


async def test_timing_anomalies_lower_score(config):
    body = json.dumps(
        {"market_sentiment": 0.9, "meme_season": 0.9, "volume_level": 0.9,
         "anomalies": ["solana_outage"], "reasoning": "сеть шатает"}
    )
    async with TimingAgent(config, client_returning(body)) as agent:
        result = await agent.get()
    assert isinstance(result, TimingResult)
    assert result.score == pytest.approx(0.8)


# --- чекер ----------------------------------------------------------------


def full_analysis() -> Analysis:
    return Analysis(
        token=token(),
        metrics=TokenMetrics(risk_score=3.0),
        audit=AuditResult(organic_buyer_share=0.8, coordinated_buying=False,
                          wash_trading=False, creator_dump_prep=False, bundled_launch=False),
        narrative=NarrativeResult(trend_fit=0.7, virality=0.7,
                                  community_signals=0.7, launch_timing=0.7),
        timing=TimingResult(market_sentiment=0.6, meme_season=0.6, volume_level=0.6),
    )


async def test_checker_uses_stronger_model(config):
    calls: list = []
    body = json.dumps({"approve": True, "reason": "чисто", "flags": [], "confidence": 0.8})
    async with CheckerAgent(config, client_returning(body, calls)) as agent:
        result = await agent.run(full_analysis())
    assert isinstance(result, CheckerResult)
    assert result.approve
    assert calls[0]["model"] == config.grok.checker_model
    assert calls[0]["model"] != config.grok.fast_model


async def test_checker_rejection_is_passed_through(config):
    body = json.dumps(
        {"approve": False, "reason": "органика не бьётся с мем-оценкой",
         "flags": ["contradiction"], "confidence": 0.9}
    )
    async with CheckerAgent(config, client_returning(body)) as agent:
        result = await agent.run(full_analysis())
    assert not result.approve
    assert result.flags == ["contradiction"]


async def test_checker_failure_means_refusal(config):
    """Ошибка проверки равна отказу, а не молчаливому пропуску."""
    async with CheckerAgent(config, client_returning("¯\\_(ツ)_/¯")) as agent:
        result = await agent.run(full_analysis())
    assert result.approve is False
    assert "agent_failure" in result.flags


async def test_checker_server_error_means_refusal(config):
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500, json={"error": "internal"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with CheckerAgent(config, client) as agent:
        result = await agent.run(full_analysis())
    assert result.approve is False
    assert len(seen) == config.grok.max_retries


async def test_client_error_is_not_retried(config):
    """401 ретраить бессмысленно — ключ от этого не починится."""
    seen: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(401, json={"error": "bad key"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with CheckerAgent(config, client) as agent:
        result = await agent.run(full_analysis())
    assert result.approve is False
    assert len(seen) == 1


# --- разбор JSON ----------------------------------------------------------


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Вот ответ: {"a": {"b": "}"}} — всё') == {"a": {"b": "}"}}


def test_extract_json_rejects_garbage():
    for bad in ("", "   ", "нет тут джейсона", "[1, 2, 3]", '{"a": 1'):
        with pytest.raises(ValueError):
            extract_json(bad)


def test_base_agent_requires_overrides(config):
    agent = GrokAgent(config)
    with pytest.raises(NotImplementedError):
        agent.build_user_message()
    with pytest.raises(NotImplementedError):
        agent.fallback("x")


# --- промпты --------------------------------------------------------------


@pytest.mark.parametrize(
    "agent_cls", [AuditorAgent, NarrativeAgent, TimingAgent, CheckerAgent]
)
def test_every_prompt_demands_bare_json(agent_cls):
    prompt = agent_cls.prompt
    assert "JSON" in prompt
    assert "markdown" in prompt.lower()
    assert prompt.strip().endswith("```.")
