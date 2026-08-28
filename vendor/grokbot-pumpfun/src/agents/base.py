"""Базовый класс агента на Grok API.

Вся общая механика вызова живёт здесь: сборка запроса, temperature=0,
строгий разбор JSON, ретраи с экспоненциальной задержкой, таймаут.

Главное правило: при любой ошибке — таймаут, HTTP, кривой JSON, невалидная
схема — агент возвращает МАКСИМАЛЬНО ПЕССИМИСТИЧНЫЙ результат, а не пустой
и не «нейтральный». Сломавшаяся проверка равна отказу. Молчаливый пропуск
на этом рынке стоит денег.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..models import Config
from ..ops import GrokOps

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GrokAgentError(RuntimeError):
    """Вызов Grok не удался после всех ретраев."""


class GrokAgent:
    """Один агент = один промпт + одна pydantic-схема ответа."""

    name: ClassVar[str] = "agent"
    prompt: ClassVar[str] = ""            # системный промпт, константа модуля агента
    result_model: ClassVar[type[BaseModel]] = BaseModel
    use_checker_model: ClassVar[bool] = False

    def __init__(
        self,
        config: Config,
        client: httpx.AsyncClient | None = None,
        ops: GrokOps | None = None,
    ) -> None:
        self.config = config
        self.grok = config.grok
        self.ops = ops              # общие на процесс ограничители; None — без них
        self._client = client
        self._owns_client = client is None

    # -- жизненный цикл ----------------------------------------------------

    @property
    def model(self) -> str:
        return self.grok.checker_model if self.use_checker_model else self.grok.fast_model

    async def __aenter__(self) -> GrokAgent:
        self._ensure_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.grok.timeout_seconds)
        return self._client

    # -- переопределяется в наследниках ------------------------------------

    def build_user_message(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError

    def fallback(self, reason: str) -> Any:
        """Пессимистичный результат. Наследник обязан вернуть худший случай."""
        raise NotImplementedError

    # -- основной вход -----------------------------------------------------

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Собрать запрос, сходить в Grok, разобрать ответ.

        Исключений наружу не выпускает: любой сбой превращается в
        пессимистичный результат.
        """
        try:
            message = self.build_user_message(*args, **kwargs)
        except Exception as exc:
            log.warning("[%s] не удалось собрать промпт: %s", self.name, exc)
            return self.fallback(f"prompt_error: {exc}")

        try:
            raw = await self._call(message)
        except GrokAgentError as exc:
            log.warning("[%s] вызов не удался: %s", self.name, exc)
            return self.fallback(str(exc))

        try:
            data = extract_json(raw)
        except ValueError as exc:
            log.warning("[%s] ответ не разобрался как JSON: %s", self.name, exc)
            return self.fallback(f"parse_error: {exc}")

        try:
            return self.result_model.model_validate(data)
        except ValidationError as exc:
            log.warning("[%s] ответ не сошёлся со схемой: %s", self.name, exc)
            return self.fallback(f"schema_error: {exc.error_count()} полей")

    # -- транспорт ---------------------------------------------------------

    def _payload(self, message: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": message},
            ],
        }

    async def _call(self, message: str) -> str:
        """POST в Grok с ретраями. Возвращает текст ответа модели."""
        client = self._ensure_client()
        headers = {
            "Authorization": f"Bearer {self.grok.key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(self.grok.max_retries):
            # Ограничители спрашиваем на каждой попытке: цепь могла
            # разомкнуться, а бюджет кончиться, пока мы ретраили.
            if self.ops is not None:
                blocked = self.ops.precheck(self.name)
                if blocked:
                    raise GrokAgentError(blocked)

            if attempt:
                await asyncio.sleep(self._backoff(attempt))
            try:
                async with self._slot():
                    resp = await client.post(
                        self.grok.base_url,
                        json=self._payload(message),
                        headers=headers,
                        timeout=self.grok.timeout_seconds,
                    )
                if resp.status_code >= 500 or resp.status_code == 429:
                    last_error = GrokAgentError(f"HTTP {resp.status_code}")
                    self._failed()
                    continue
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                self._failed()
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = GrokAgentError(f"неожиданная форма ответа: {exc}")
                self._failed()
            except httpx.HTTPStatusError as exc:
                # 4xx кроме 429 ретраить бессмысленно: ключ или запрос не те
                self._failed()
                raise GrokAgentError(f"HTTP {exc.response.status_code}") from exc
            else:
                if self.ops is not None:
                    self.ops.record_success(self.name, body.get("usage"))
                return content

        raise GrokAgentError(f"после {self.grok.max_retries} попыток: {last_error}")

    def _backoff(self, attempt: int) -> float:
        """Экспоненциальная задержка с джиттером.

        Джиттер важен: без него пачка агентов, стартовавшая одновременно,
        ретраится тоже одновременно и добивает и без того больной API.
        """
        base = self.grok.retry_base_delay * (2 ** (attempt - 1))
        delay = base * (0.5 + random.random())
        log.debug("[%s] ретрай %d через %.2fs", self.name, attempt, delay)
        return delay

    def _slot(self) -> Any:
        if self.ops is None:
            return _NullSlot()
        return self.ops.slot(self.name)

    def _failed(self) -> None:
        if self.ops is not None:
            self.ops.record_failure(self.name)


class _NullSlot:
    """Заглушка очереди для агента без ограничителей (тесты, одиночный вызов)."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


# --------------------------------------------------------------------------
# Разбор ответа
# --------------------------------------------------------------------------

JSON_ONLY = (
    "Ответь ТОЛЬКО валидным JSON указанной формы. "
    "Без пояснений, без текста до и после, без markdown-обёртки и без ```."
)


def extract_json(text: str) -> dict[str, Any]:
    """Достать JSON-объект из ответа модели.

    Промпт требует чистый JSON, но модели иногда всё равно заворачивают его
    в ```json. Снимаем обёртку и вырезаем первый сбалансированный объект.
    """
    if not text or not text.strip():
        raise ValueError("пустой ответ")

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = json.loads(_first_object(cleaned))

    if not isinstance(data, dict):
        raise ValueError(f"ожидался объект, пришёл {type(data).__name__}")
    return data


def _first_object(text: str) -> str:
    """Первый сбалансированный {...} в строке."""
    start = text.find("{")
    if start == -1:
        raise ValueError("в ответе нет JSON-объекта")
    depth = 0
    in_string = False
    escaped = False
    for i, ch in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("незакрытый JSON-объект")
