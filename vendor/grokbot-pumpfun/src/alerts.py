"""Уведомления во внешний webhook.

Пайплайн работает без присмотра, и узнать о том, что цепь разомкнулась или
дневной лимит выбран, сейчас можно только заглянув в лог. Отправка событий
наружу закрывает этот разрыв.

Три правила, из которых всё остальное следует:
  * выключено по умолчанию — пустой `webhook_url` не шлёт ничего;
  * никогда не мешает торговле — отправка идёт фоновой задачей, любая
    ошибка сети остаётся в логе и наружу не всплывает;
  * не превращается в спам — поток событий ограничен по частоте, лишнее
    считается и выбрасывается, а не копится в очереди.

Формат сообщения намеренно простой: `text` понимает Slack, `content` —
Discord, остальные поля не мешают ни тем, ни другим. Для Telegram нужен
промежуточный релей: у него другой протокол.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from typing import Any

import httpx

from .models import AlertsConfig

log = logging.getLogger(__name__)

# События, которые умеет слать пайплайн. Набор в конфиге — подмножество.
KNOWN_EVENTS = (
    "started", "stopped", "buy", "close", "rug", "breaker", "halted", "stalled", "blind",
)


class Notifier:
    """Отправка событий в webhook. Работает и выключенным — тогда молча."""

    def __init__(self, config: AlertsConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client
        self._owns_client = client is None
        self._tasks: set[asyncio.Task] = set()
        self._recent: deque[float] = deque()
        self.sent = 0
        self.dropped = 0
        self.failed = 0

    @property
    def enabled(self) -> bool:
        return bool(self.config.webhook_url.get_secret_value().strip())

    def wants(self, event: str) -> bool:
        return self.enabled and event in self.config.events

    # -- отправка ----------------------------------------------------------

    def notify(self, event: str, text: str, **fields: Any) -> asyncio.Task | None:
        """Поставить событие в отправку. Возвращает задачу или None.

        Синхронный вызов: торговая логика не должна ждать сеть ради
        уведомления.
        """
        if not self.wants(event):
            return None
        if not self._allow_now():
            self.dropped += 1
            return None
        task = asyncio.create_task(self._send(event, text, fields), name=f"alert-{event}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _allow_now(self) -> bool:
        """Скользящее окно в минуту. Всплеск лончей не должен стать всплеском писем."""
        now = time.monotonic()
        while self._recent and now - self._recent[0] > 60.0:
            self._recent.popleft()
        if len(self._recent) >= self.config.max_per_minute:
            if self.dropped == 0:
                log.warning("уведомления придержаны: больше %d в минуту",
                            self.config.max_per_minute)
            return False
        self._recent.append(now)
        return True

    async def _send(self, event: str, text: str, fields: dict[str, Any]) -> None:
        payload = {
            "event": event,
            "text": f"[grokbot] {text}",
            "content": f"[grokbot] {text}",   # Discord читает это поле
            "fields": fields,
        }
        try:
            client = self._ensure_client()
            response = await client.post(
                self.config.webhook_url.get_secret_value(),
                json=payload,
                timeout=self.config.timeout_seconds,
            )
            if response.status_code >= 400:
                self.failed += 1
                # URL не печатаем: в нём токен
                log.warning("webhook ответил %d на событие %s", response.status_code, event)
                return
            self.sent += 1
        except Exception as exc:
            self.failed += 1
            log.warning("уведомление %s не ушло: %s", event, exc)

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
        return self._client

    # -- завершение --------------------------------------------------------

    async def aclose(self, grace: float = 5.0) -> None:
        """Дать уйти последним уведомлениям и закрыть соединение."""
        if self._tasks:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*self._tasks, return_exceptions=True), timeout=grace
                )
        for task in list(self._tasks):
            task.cancel()
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def snapshot(self) -> dict[str, Any]:
        return {"sent": self.sent, "dropped": self.dropped, "failed": self.failed}
