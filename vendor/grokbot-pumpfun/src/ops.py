"""Эксплуатационная обвязка: ограничители, метрики, health, heartbeat.

Всё, что нужно процессу, который работает сутками без присмотра, и ничего,
что нужно торговой логике. Зависимостей, кроме стандартной библиотеки,
здесь нет: health-эндпоинт написан на asyncio.start_server, а не на веб-
фреймворке, чтобы контейнер оставался маленьким.

Три ограничителя расхода Grok, каждый закрывает свой отказ:
  * `RateLimiter`  — не долбить API чаще договорённого;
  * `CallBudget`   — не сжечь дневной бюджет за один всплеск лончей;
  * `CircuitBreaker` — перестать звонить туда, где всё равно не отвечают.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from .models import Config

log = logging.getLogger(__name__)


def utc_day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------
# Метрики
# --------------------------------------------------------------------------


class Metrics:
    """Счётчики и мгновенные значения. Без внешнего сборщика — просто в память."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self.clock = clock
        self.started_at = clock()
        self.counters: Counter[str] = Counter()
        self.gauges: dict[str, float] = {}

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def gauge(self, name: str, value: float) -> None:
        self.gauges[name] = value

    @property
    def uptime_seconds(self) -> float:
        return max(0.0, self.clock() - self.started_at)

    def snapshot(self) -> dict[str, Any]:
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "counters": dict(sorted(self.counters.items())),
            "gauges": dict(sorted(self.gauges.items())),
        }

    def prometheus(self, prefix: str = "grokbot") -> str:
        """Текстовая экспозиция для Prometheus. Без зависимостей."""
        lines = [f"{prefix}_uptime_seconds {self.uptime_seconds:.1f}"]
        lines += [
            f"{prefix}_{_safe(name)}_total {count}"
            for name, count in sorted(self.counters.items())
        ]
        lines += [
            f"{prefix}_{_safe(name)} {value}"
            for name, value in sorted(self.gauges.items())
        ]
        return "\n".join(lines) + "\n"


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name).strip("_").lower()


# --------------------------------------------------------------------------
# Ограничители
# --------------------------------------------------------------------------


class RateLimiter:
    """Ведро токенов: не чаще `per_minute` вызовов, всплеск не больше `burst`."""

    def __init__(
        self,
        per_minute: float,
        burst: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rate = max(0.001, per_minute) / 60.0        # токенов в секунду
        self.capacity = burst if burst is not None else max(1.0, per_minute / 6.0)
        self.clock = clock
        self.tokens = self.capacity
        self.updated = clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self.clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now

    def delay_for_next(self) -> float:
        """Сколько ждать до следующего разрешённого вызова. 0 — можно сразу."""
        self._refill()
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.rate

    async def acquire(self) -> float:
        """Дождаться права на вызов. Возвращает, сколько пришлось ждать."""
        waited = 0.0
        async with self._lock:
            while True:
                delay = self.delay_for_next()
                if delay <= 0:
                    self.tokens -= 1.0
                    return waited
                waited += delay
                await asyncio.sleep(delay)


class CircuitBreaker:
    """Размыкается после N сбоев подряд и не пускает вызовы `cooldown` секунд.

    Смысл не в экономии, а в том, чтобы при лежащем API пайплайн быстро и
    честно отказывал (то есть не покупал), а не висел на таймаутах.
    """

    def __init__(
        self,
        failures: int,
        cooldown: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = max(1, failures)
        self.cooldown = max(0.0, cooldown)
        self.clock = clock
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self.trips = 0

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if self.clock() - self.opened_at >= self.cooldown:
            # Пробуем снова: полуоткрытое состояние, один вызов на разведку.
            self.opened_at = None
            self.consecutive_failures = self.threshold - 1
            log.info("цепь Grok снова замкнута, пробуем разведочный вызов")
            return False
        return True

    @property
    def state(self) -> str:
        if self.is_open:
            return "open"
        return "half-open" if self.consecutive_failures else "closed"

    def remaining_cooldown(self) -> float:
        if self.opened_at is None:
            return 0.0
        return max(0.0, self.cooldown - (self.clock() - self.opened_at))

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold and self.opened_at is None:
            self.opened_at = self.clock()
            self.trips += 1
            log.error("цепь Grok разомкнута: %d сбоев подряд, пауза %.0fs",
                      self.consecutive_failures, self.cooldown)


class CallBudget:
    """Потолок вызовов Grok в сутки. Сам сбрасывается в полночь UTC."""

    def __init__(
        self,
        max_per_day: int,
        clock: Callable[[], float] = time.time,
        spent: int = 0,
    ) -> None:
        self.max_per_day = max(1, max_per_day)
        self.clock = clock
        self.day = utc_day(clock())
        self.spent = spent
        self._warned = False

    def _roll(self) -> None:
        today = utc_day(self.clock())
        if today != self.day:
            log.info("бюджет вызовов Grok сброшен: за %s потрачено %d", self.day, self.spent)
            self.day = today
            self.spent = 0
            self._warned = False

    @property
    def remaining(self) -> int:
        self._roll()
        return max(0, self.max_per_day - self.spent)

    def try_spend(self, amount: int = 1) -> bool:
        self._roll()
        if self.spent + amount > self.max_per_day:
            if not self._warned:
                log.error("дневной бюджет вызовов Grok исчерпан (%d), до полуночи UTC "
                          "агенты не вызываются", self.max_per_day)
                self._warned = True
            return False
        self.spent += amount
        if self.remaining <= self.max_per_day // 10 and not self._warned:
            log.warning("бюджет вызовов Grok на исходе: осталось %d из %d",
                        self.remaining, self.max_per_day)
        return True


# --------------------------------------------------------------------------
# Обвязка агентов
# --------------------------------------------------------------------------


class GrokOps:
    """Общие на весь процесс ограничители и счётчики вызовов Grok."""

    def __init__(self, config: Config, metrics: Metrics | None = None, spent: int = 0) -> None:
        ops = config.ops
        self.metrics = metrics or Metrics()
        self.limiter = RateLimiter(ops.grok_calls_per_minute)
        self.breaker = CircuitBreaker(ops.breaker_failures, ops.breaker_cooldown_seconds)
        self.budget = CallBudget(ops.max_grok_calls_per_day, spent=spent)
        self.semaphore = asyncio.Semaphore(max(1, ops.grok_max_concurrency))
        self.tokens_in = 0
        self.tokens_out = 0

    def precheck(self, agent: str) -> str | None:
        """Причина не звонить в Grok прямо сейчас, или None."""
        if self.breaker.is_open:
            self.metrics.inc(f"grok_blocked_breaker_{agent}")
            return f"цепь разомкнута, осталось {self.breaker.remaining_cooldown():.0f}s"
        if not self.budget.try_spend():
            self.metrics.inc(f"grok_blocked_budget_{agent}")
            return f"дневной бюджет вызовов исчерпан ({self.budget.max_per_day})"
        return None

    @asynccontextmanager
    async def slot(self, agent: str):
        """Место в очереди: параллелизм и частота."""
        async with self.semaphore:
            waited = await self.limiter.acquire()
            if waited > 0:
                self.metrics.inc(f"grok_throttled_{agent}")
            self.metrics.inc(f"grok_calls_{agent}")
            yield

    def record_success(self, agent: str, usage: dict[str, Any] | None = None) -> None:
        self.breaker.record_success()
        self.metrics.inc(f"grok_ok_{agent}")
        if usage:
            self.tokens_in += int(usage.get("prompt_tokens") or 0)
            self.tokens_out += int(usage.get("completion_tokens") or 0)
            self.metrics.gauge("grok_tokens_in", self.tokens_in)
            self.metrics.gauge("grok_tokens_out", self.tokens_out)

    def record_failure(self, agent: str) -> None:
        self.breaker.record_failure()
        self.metrics.inc(f"grok_fail_{agent}")

    def snapshot(self) -> dict[str, Any]:
        return {
            "breaker": self.breaker.state,
            "breaker_trips": self.breaker.trips,
            "budget_spent": self.budget.spent,
            "budget_remaining": self.budget.remaining,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


# --------------------------------------------------------------------------
# Health-эндпоинт
# --------------------------------------------------------------------------

StatusProvider = Callable[[], dict[str, Any]]


class HealthServer:
    """Минимальный HTTP: GET /healthz (JSON) и GET /metrics (Prometheus).

    Ровно две ручки и никакого фреймворка. `status` в ответе решает код:
    "ok" -> 200, всё остальное -> 503, чтобы оркестратор перезапустил.
    """

    def __init__(
        self,
        host: str,
        port: int,
        provider: StatusProvider,
        metrics: Metrics,
    ) -> None:
        self.host = host
        self.port = port
        self.provider = provider
        self.metrics = metrics
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> asyncio.AbstractServer | None:
        if not self.port:
            return None
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("health-эндпоинт слушает http://%s:%d/healthz", self.host, self.port)
        return self._server

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            request = await asyncio.wait_for(reader.readline(), timeout=5.0)
            path = request.decode("latin-1", "replace").split(" ")[1] if b" " in request else "/"
            body, content_type, code = self._route(path.split("?")[0])
            payload = body.encode("utf-8")
            writer.write(
                f"HTTP/1.1 {code} {'OK' if code == 200 else 'ERR'}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(payload)}\r\n"
                "Connection: close\r\n\r\n".encode("latin-1") + payload
            )
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        except Exception as exc:
            log.warning("health-запрос упал: %s", exc)
        finally:
            writer.close()

    def _route(self, path: str) -> tuple[str, str, int]:
        if path == "/metrics":
            return self.metrics.prometheus(), "text/plain; version=0.0.4", 200
        if path in ("/", "/healthz", "/health"):
            try:
                status = self.provider()
            except Exception as exc:            # провайдер не должен ронять health
                status = {"status": "error", "error": str(exc)}
            code = 200 if status.get("status") == "ok" else 503
            return json.dumps(status, ensure_ascii=False, indent=2), "application/json", code
        return json.dumps({"error": "not found"}), "application/json", 404


# --------------------------------------------------------------------------
# Heartbeat
# --------------------------------------------------------------------------


class Heartbeat:
    """Периодическая строка живости в лог: по ней видно, что процесс дышит."""

    def __init__(self, interval: float, provider: StatusProvider) -> None:
        self.interval = max(1.0, interval)
        self.provider = provider
        self._task: asyncio.Task | None = None

    def line(self) -> str:
        status = self.provider()
        parts = [f"{key}={value}" for key, value in status.items()
                 if not isinstance(value, (dict, list))]
        return " ".join(parts)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                log.info("жив: %s", self.line())
            except Exception as exc:
                log.warning("heartbeat не собрался: %s", exc)

    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run(), name="heartbeat")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None


async def drain(tasks: set[asyncio.Task], grace: float) -> tuple[int, int]:
    """Дать задачам в работе доделаться, остальные снять. (доделали, сняли)."""
    if not tasks:
        return 0, 0
    log.info("останавливаемся: ждём %d задач в работе до %.0fs", len(tasks), grace)
    done, pending = await asyncio.wait(tasks, timeout=grace)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
        log.warning("%d задач не уложились в grace и сняты", len(pending))
    return len(done), len(pending)


def install_signal_handlers(stop: Callable[[str], Any]) -> None:
    """SIGINT и SIGTERM переводятся в аккуратную остановку, а не в KeyboardInterrupt."""
    import signal

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop, sig.name)
        except NotImplementedError:      # Windows
            # sig связываем значением по умолчанию: иначе оба обработчика
            # доложат об одном сигнале — том, что остался в конце цикла
            signal.signal(sig, lambda *_, name=sig.name: stop(name))


async def cancel_and_wait(task: asyncio.Task | None) -> None:
    """Снять задачу и дождаться её конца, не пробрасывая CancelledError."""
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


AsyncCallable = Callable[[], Awaitable[Any]]
