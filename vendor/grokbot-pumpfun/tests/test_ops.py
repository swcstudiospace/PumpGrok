"""Эксплуатационная обвязка: ограничители расхода Grok, метрики, health.

Сеть здесь настоящая только в тестах health-эндпоинта, и только на
127.0.0.1 — наружу ничего не ходит.
"""

import asyncio
import json
import socket

import httpx
import pytest

from src.agents import CheckerAgent
from src.models import Config
from src.ops import (
    CallBudget,
    CircuitBreaker,
    GrokOps,
    HealthServer,
    Heartbeat,
    Metrics,
    RateLimiter,
    drain,
)


class FakeClock:
    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def config() -> Config:
    cfg = Config()
    cfg.grok.api_key = "xai-test-key-1234567890"
    cfg.grok.retry_base_delay = 0.0
    cfg.grok.max_retries = 2
    cfg.ops.breaker_failures = 2
    cfg.ops.breaker_cooldown_seconds = 60.0
    cfg.ops.max_grok_calls_per_day = 10
    cfg.ops.grok_calls_per_minute = 6000
    return cfg


# --- ведро токенов --------------------------------------------------------


def test_limiter_allows_burst_then_throttles():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=3, clock=clock)
    for _ in range(3):
        assert limiter.delay_for_next() == 0.0
        limiter.tokens -= 1.0
    assert limiter.delay_for_next() == pytest.approx(1.0, abs=0.01)


def test_limiter_refills_over_time():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=1, clock=clock)
    limiter.tokens = 0.0
    clock.advance(1.0)
    assert limiter.delay_for_next() == 0.0


def test_limiter_does_not_overfill():
    clock = FakeClock()
    limiter = RateLimiter(per_minute=60, burst=2, clock=clock)
    clock.advance(3600)
    limiter._refill()
    assert limiter.tokens == 2.0


async def test_limiter_serializes_calls():
    limiter = RateLimiter(per_minute=60_000, burst=1)     # 1000/с, ждать почти не надо
    waited = [await limiter.acquire() for _ in range(5)]
    assert all(w >= 0 for w in waited)


# --- предохранитель -------------------------------------------------------


def test_breaker_opens_after_threshold():
    clock = FakeClock()
    breaker = CircuitBreaker(failures=3, cooldown=60, clock=clock)
    for _ in range(2):
        breaker.record_failure()
    assert not breaker.is_open
    assert breaker.state == "half-open"
    breaker.record_failure()
    assert breaker.is_open
    assert breaker.state == "open"
    assert breaker.trips == 1


def test_success_resets_failures():
    breaker = CircuitBreaker(failures=3, cooldown=60, clock=FakeClock())
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert not breaker.is_open


def test_breaker_closes_after_cooldown():
    clock = FakeClock()
    breaker = CircuitBreaker(failures=1, cooldown=60, clock=clock)
    breaker.record_failure()
    assert breaker.is_open
    assert breaker.remaining_cooldown() == pytest.approx(60.0)

    clock.advance(59)
    assert breaker.is_open
    clock.advance(2)
    assert not breaker.is_open          # разведочный вызов разрешён


def test_reopens_immediately_if_probe_fails():
    clock = FakeClock()
    breaker = CircuitBreaker(failures=2, cooldown=10, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    clock.advance(11)
    assert not breaker.is_open          # полуоткрыто
    breaker.record_failure()            # разведка не удалась
    assert breaker.is_open
    assert breaker.trips == 2


# --- дневной бюджет -------------------------------------------------------


def test_budget_counts_down():
    budget = CallBudget(max_per_day=3, clock=FakeClock())
    assert budget.remaining == 3
    assert budget.try_spend()
    assert budget.try_spend()
    assert budget.try_spend()
    assert not budget.try_spend()
    assert budget.remaining == 0


def test_budget_resets_next_day():
    clock = FakeClock(start=1_800_000_000.0)
    budget = CallBudget(max_per_day=2, clock=clock)
    budget.try_spend()
    budget.try_spend()
    assert not budget.try_spend()
    clock.advance(86_400)
    assert budget.try_spend()
    assert budget.spent == 1


def test_budget_restores_spent_count():
    """После рестарта бюджет продолжается, а не начинается заново."""
    budget = CallBudget(max_per_day=5, clock=FakeClock(), spent=4)
    assert budget.remaining == 1
    assert budget.try_spend()
    assert not budget.try_spend()


# --- метрики --------------------------------------------------------------


def test_metrics_snapshot_and_prometheus():
    metrics = Metrics(clock=FakeClock())
    metrics.inc("grok_ok_auditor")
    metrics.inc("grok_ok_auditor")
    metrics.gauge("open_positions", 2)
    snapshot = metrics.snapshot()
    assert snapshot["counters"]["grok_ok_auditor"] == 2
    assert snapshot["gauges"]["open_positions"] == 2

    text = metrics.prometheus()
    assert "grokbot_grok_ok_auditor_total 2" in text
    assert "grokbot_open_positions 2" in text
    assert text.endswith("\n")


# --- обвязка агентов ------------------------------------------------------


def failing_client(seen: list) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(500, json={"error": "internal"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_client(seen: list) -> httpx.AsyncClient:
    body = json.dumps({"approve": False, "reason": "нет", "flags": [], "confidence": 0.5})

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": body}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30},
        })

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def analysis():
    from src.models import Analysis, Token
    return Analysis(token=Token(mint="M"))


async def test_open_breaker_stops_calling_grok(config):
    seen: list = []
    ops = GrokOps(config)
    async with CheckerAgent(config, failing_client(seen), ops) as agent:
        await agent.run(analysis())          # 2 попытки, 2 сбоя -> цепь разомкнута
        assert ops.breaker.is_open
        before = len(seen)
        result = await agent.run(analysis())
    assert len(seen) == before               # второй раз в сеть не пошли
    assert result.approve is False           # и это отказ, а не пропуск
    assert "agent_failure" in result.flags


async def test_exhausted_budget_stops_calling_grok(config):
    config.ops.max_grok_calls_per_day = 1
    seen: list = []
    ops = GrokOps(config)
    async with CheckerAgent(config, ok_client(seen), ops) as agent:
        first = await agent.run(analysis())
        second = await agent.run(analysis())
    assert len(seen) == 1
    assert first.reason == "нет"
    assert second.approve is False
    assert ops.budget.remaining == 0


async def test_success_records_token_usage(config):
    seen: list = []
    ops = GrokOps(config)
    async with CheckerAgent(config, ok_client(seen), ops) as agent:
        await agent.run(analysis())
    assert ops.tokens_in == 120
    assert ops.tokens_out == 30
    assert ops.metrics.counters["grok_ok_checker"] == 1
    assert ops.snapshot()["breaker"] == "closed"


async def test_agent_works_without_ops(config):
    """Ограничители опциональны: без них агент ведёт себя как раньше."""
    seen: list = []
    async with CheckerAgent(config, ok_client(seen)) as agent:
        result = await agent.run(analysis())
    assert result.reason == "нет"
    assert len(seen) == 1


# --- health ---------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def http_get(port: int, path: str) -> tuple[int, str]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    raw = await reader.read()
    writer.close()
    head, _, body = raw.decode().partition("\r\n\r\n")
    return int(head.split(" ")[1]), body


async def test_health_reports_ok_and_metrics():
    metrics = Metrics()
    metrics.inc("buys")
    port = free_port()
    server = HealthServer("127.0.0.1", port, lambda: {"status": "ok", "open": 1}, metrics)
    await server.start()
    try:
        code, body = await http_get(port, "/healthz")
        assert code == 200
        assert json.loads(body)["open"] == 1

        code, body = await http_get(port, "/metrics")
        assert code == 200
        assert "grokbot_buys_total 1" in body

        code, _ = await http_get(port, "/нет-такого")
        assert code == 404
    finally:
        await server.stop()


async def test_health_returns_503_when_not_ok():
    port = free_port()
    server = HealthServer("127.0.0.1", port, lambda: {"status": "degraded"}, Metrics())
    await server.start()
    try:
        code, _ = await http_get(port, "/healthz")
        assert code == 503
    finally:
        await server.stop()


async def test_health_survives_broken_provider():
    port = free_port()

    def provider():
        raise RuntimeError("состояние не собралось")

    server = HealthServer("127.0.0.1", port, provider, Metrics())
    await server.start()
    try:
        code, body = await http_get(port, "/healthz")
        assert code == 503
        assert "состояние не собралось" in body
    finally:
        await server.stop()


async def test_disabled_health_does_not_listen():
    server = HealthServer("127.0.0.1", 0, lambda: {"status": "ok"}, Metrics())
    assert await server.start() is None
    await server.stop()


# --- остановка ------------------------------------------------------------


async def test_drain_waits_for_quick_tasks():
    async def quick() -> str:
        await asyncio.sleep(0.01)
        return "готово"

    tasks = {asyncio.create_task(quick()) for _ in range(3)}
    done, cancelled = await drain(tasks, grace=1.0)
    assert (done, cancelled) == (3, 0)


async def test_drain_cancels_stuck_tasks():
    async def stuck() -> None:
        await asyncio.sleep(3600)

    tasks = {asyncio.create_task(stuck())}
    done, cancelled = await drain(tasks, grace=0.05)
    assert (done, cancelled) == (0, 1)


async def test_drain_on_empty_set():
    assert await drain(set(), grace=1.0) == (0, 0)


async def test_heartbeat_line_is_flat():
    beat = Heartbeat(1.0, lambda: {"status": "ok", "open": 2, "nested": {"a": 1}})
    line = beat.line()
    assert "status=ok" in line and "open=2" in line
    assert "nested" not in line
