"""Grok agent base: one prompt plus one response schema, on injected time.

Port of the retired oracle ``src/agents/base.py``. The retry loop keeps
its vendor shape (ops precheck on every attempt, one backoff sleep between
attempts, no retry on 4xx other than 429), but wall time is gone:
``asyncio.sleep`` becomes ``clock.sleep`` and ``random.random`` becomes the
injected ``rng`` from ``make_rng``. The request posts to the configured
``base_url`` plus ``/chat/completions`` per R48; model choice comes from
settings (strong for the checker, fast for the rest), never hard-coded.
Prompts are translated to English; because prompt text feeds the canonical
request hash, the smoke LLM records are authored last.

Untrusted model output crosses here: it is parsed as data into pydantic
models, never executed. Prompts stay code constants (T-02-07).
"""

from __future__ import annotations

import json
import logging
from random import Random
from typing import Any, ClassVar, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from pumpgrok.config.settings import GrokSettings
from pumpgrok.core.llm import GrokOps
from pumpgrok.replay.clock import Clock

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

CHAT_COMPLETIONS_PATH = "/chat/completions"

JSON_ONLY = (
    "Reply with a single JSON object only, no markdown fences, no commentary. "
    "Every required key must be present."
)


class GrokAgentError(RuntimeError):
    """A Grok call failed after all retries."""


class GrokAgent:
    """One agent: one system prompt plus one pydantic response schema."""

    name: ClassVar[str] = "agent"
    prompt: ClassVar[str] = ""
    result_model: ClassVar[type[BaseModel]] = BaseModel
    use_checker_model: ClassVar[bool] = False

    @property
    def model(self) -> str:
        """Strong model for the checker, fast model for every other agent."""
        if self.use_checker_model:
            return self._grok.strong_model
        return self._grok.fast_model

    def __init__(
        self,
        grok: GrokSettings,
        *,
        clock: Clock,
        rng: Random,
        client: httpx.AsyncClient | None = None,
        ops: GrokOps | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._grok = grok
        self._clock = clock
        self._rng = rng
        self.ops = ops
        self._client = client
        self._owns_client = client is None
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    @property
    def endpoint(self) -> str:
        """SDK base URL plus the chat-completions path (never a full path setting)."""
        return self._grok.base_url.rstrip("/") + CHAT_COMPLETIONS_PATH

    async def __aenter__(self) -> GrokAgent:
        self._ensure_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the owned client. Shared clients stay open for their owner."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        return self._client

    def build_user_message(self, *args: Any, **kwargs: Any) -> str:
        """Assemble the user message. Heirs map their inputs to JSON here."""
        raise NotImplementedError

    def fallback(self, reason: str) -> Any:
        """Pessimistic result. Heirs must return the worst case, never raise."""
        raise NotImplementedError

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Build the prompt, call Grok, parse the answer.

        Never raises: every failure becomes the pessimistic fallback.
        """
        try:
            message = self.build_user_message(*args, **kwargs)
        except Exception as exc:
            log.warning("[%s] could not build prompt: %s", self.name, exc)
            return self.fallback(f"prompt_error: {exc}")

        try:
            raw = await self._call(message)
        except GrokAgentError as exc:
            log.warning("[%s] call failed: %s", self.name, exc)
            return self.fallback(str(exc))

        try:
            data = extract_json(raw)
        except ValueError as exc:
            log.warning("[%s] answer is not JSON: %s", self.name, exc)
            return self.fallback(f"parse_error: {exc}")

        try:
            return self.result_model.model_validate(data)
        except ValidationError as exc:
            log.warning("[%s] answer violates schema: %s", self.name, exc)
            return self.fallback(f"schema_error: {exc.error_count()} fields")

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
        """POST to Grok with retries. Returns the model reply text."""
        client = self._ensure_client()
        headers = {
            "Authorization": f"Bearer {self._grok.api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            # Ask the limiters on every attempt: the budget may have run
            # out, or a Phase 4 breaker may have opened, mid-retry.
            if self.ops is not None:
                blocked = self.ops.precheck(self.name)
                if blocked:
                    raise GrokAgentError(blocked)

            if attempt:
                await self._clock.sleep(self._backoff(attempt))
            try:
                async with self._slot():
                    resp = await client.post(
                        self.endpoint,
                        json=self._payload(message),
                        headers=headers,
                        timeout=self._timeout_seconds,
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
                last_error = GrokAgentError(f"unexpected answer shape: {exc}")
                self._failed()
            except httpx.HTTPStatusError as exc:
                # 4xx other than 429 is not worth a retry: the key or the
                # request is wrong, not the network.
                self._failed()
                raise GrokAgentError(f"HTTP {exc.response.status_code}") from exc
            else:
                if self.ops is not None:
                    usage = body.get("usage") if isinstance(body, dict) else None
                    self.ops.record_success(self.name, usage)
                return str(content)

        raise GrokAgentError(f"after {self._max_retries} attempts: {last_error}")

    def _backoff(self, attempt: int) -> float:
        """Exponential delay with jitter.

        Jitter matters: without it a pack of agents that started together
        retries together and finishes off an already sick API.
        """
        base = self._retry_base_delay * (2 ** (attempt - 1))
        delay: float = base * (0.5 + self._rng.random())
        log.debug("[%s] retry %d in %.2fs", self.name, attempt, delay)
        return delay

    def _slot(self) -> Any:
        if self.ops is None:
            return _NullSlot()
        return self.ops.slot(self.name)

    def _failed(self) -> None:
        if self.ops is not None:
            self.ops.record_failure(self.name)


class _NullSlot:
    """Queue placeholder for an agent without limiters (tests, single call)."""

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: Any) -> None:
        return None


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a model answer.

    Accepts a bare object or one wrapped in prose or fences; the first
    balanced ``{...}`` wins. Raises ``ValueError`` when nothing parses.
    """
    stripped = text.strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    candidate = _first_object(stripped)
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("top-level JSON value is not an object")
    return data


def _first_object(text: str) -> str:
    """The first balanced {...} in a string. Braces inside strings are skipped."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in answer")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unclosed JSON object")
