"""x.ai and replay transports behind the gateway (GRK-05, GRK-06, GRK-08).

``XaiTransport`` is the live ``GrokTransport``. It refuses to exist without a
key, sends only prompts and schemas registered by digest, bounds the call
deadline and the answer size, and returns text only after strict parsing
against the registered result model. Every failure raises; the gateway turns
it into a fallback and a negative cache entry.

The transport neither spends nor retries. The gateway charges the layered
budget once per admitted call and owns the breaker, so one admitted request
costs one charge. Usage is counted on ``GrokOps`` without a second spend.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.llm import GrokOps
from pumpgrok.grok.gateway import (
    TRANSPORT_DEADLINE_S,
    GrokGateway,
    GrokOutcome,
    GrokRequest,
    _request_key,
    prefilter,
    sanitize,
)
from pumpgrok.grok.sanitize import StrictParseError, parse_strict
from pumpgrok.replay.clock import Clock
from pumpgrok.replay.recorder import ReplayLlm

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "MAX_RESPONSE_BYTES",
    "GrokTransportError",
    "MissingGrokKey",
    "ReplayTransport",
    "XaiTransport",
    "admit_replay",
]

CHAT_COMPLETIONS_PATH = "/chat/completions"
MAX_RESPONSE_BYTES = 64 * 1024


class MissingGrokKey(PumpgrokError):
    """No x.ai key is configured. No request may be built or sent."""

    code = "grok_key_missing"


class GrokTransportError(PumpgrokError):
    """The x.ai call failed or its answer was refused. The gateway counts it as a failure."""

    code = "grok_transport_error"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class XaiTransport:
    """POST one registered prompt and one user message to x.ai; return a validated answer."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        client: httpx.AsyncClient,
        prompts: Mapping[str, str],
        schemas: Mapping[str, type[BaseModel]],
        ops: GrokOps | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise MissingGrokKey("grok API key is empty; the transport refuses to send")
        for prompt_sha, prompt in prompts.items():
            if _digest(prompt) != prompt_sha:
                raise ValueError("prompt key is not the sha256 of its prompt text")
        self._api_key = api_key
        self._endpoint = base_url.rstrip("/") + CHAT_COMPLETIONS_PATH
        self._client = client
        self._prompts = dict(prompts)
        self._schemas = dict(schemas)
        self._ops = ops

    async def __call__(self, request: GrokRequest, text: str) -> str:
        system = self._prompts.get(request.prompt_sha)
        if system is None:
            raise GrokTransportError("unknown prompt; no request sent")
        model = self._schemas.get(request.schema)
        if model is None:
            raise GrokTransportError("unknown schema; no request sent")

        payload = {
            "model": request.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        status, raw = await self._fetch_bytes(request, headers, payload)
        if status != 200:
            self._failed(request)
            raise GrokTransportError("x.ai answer refused", status=status)

        try:
            body = json.loads(raw)
            content = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            self._failed(request)
            raise GrokTransportError("x.ai envelope is malformed") from None
        if not isinstance(content, str):
            self._failed(request)
            raise GrokTransportError("x.ai answer is not text")

        try:
            parse_strict(content, model)
        except StrictParseError:
            self._failed(request)
            raise GrokTransportError("x.ai answer failed strict parse") from None

        if self._ops is not None:
            self._ops.gateway_call(request.agent, _usage(body))
        return content

    async def _fetch_bytes(
        self, request: GrokRequest, headers: dict[str, str], payload: dict[str, Any]
    ) -> tuple[int, bytes]:
        try:
            # EXEC-EX-18: stream and stop at the size cap; never buffer unbounded.
            status = 0
            chunks: list[bytes] = []
            total = 0
            async with self._client.stream(
                "POST", self._endpoint, headers=headers, json=payload, timeout=TRANSPORT_DEADLINE_S
            ) as response:
                status = response.status_code
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        self._failed(request)
                        raise GrokTransportError("x.ai answer refused", status=status) from None
                    chunks.append(chunk)
        except httpx.HTTPError:
            self._failed(request)
            raise GrokTransportError("x.ai request failed") from None
        return status, b"".join(chunks)

    def _failed(self, request: GrokRequest) -> None:
        if self._ops is not None:
            self._ops.record_failure(request.agent)


def _usage(body: Any) -> dict[str, Any] | None:
    usage = body.get("usage") if isinstance(body, dict) else None
    return usage if isinstance(usage, dict) else None


class ReplayTransport:
    """Recorded model outcomes behind the gateway. It has no HTTP client, so no socket.

    The request key is the gateway's own key, so a live recording and its replay
    share one hash. A request that needs a call and has no record raises
    ``ReplayMissingRecord``. Use ``admit_replay``: it checks the record before the
    gateway, so a miss never reaches the breaker, the cache or the fallback ladder.
    """

    def __init__(self, llm: ReplayLlm) -> None:
        self._llm = llm

    def require(self, request: GrokRequest) -> None:
        """Raise ``ReplayMissingRecord`` unless ``request`` has a recorded outcome."""
        self._llm.lookup(_request_key(request, sanitize(request.text)))

    async def __call__(self, request: GrokRequest, text: str) -> str:
        record = self._llm.lookup(_request_key(request, text))
        if record.outcome == "ok":
            content = record.response.get("content")
            if isinstance(content, str):
                return content
            raise GrokTransportError("recorded ok outcome carries no answer text")
        if record.outcome == "timeout":
            raise TimeoutError("recorded timeout outcome")
        raise GrokTransportError("recorded error outcome")


async def admit_replay(
    gateway: GrokGateway,
    replay: ReplayTransport,
    request: GrokRequest,
    *,
    clock: Clock,
) -> GrokOutcome:
    """Admit one request on the replay path. A needed call with no record raises.

    A prefilter skip spends nothing and needs no record, so it passes through.
    """
    if prefilter(request.candidate, now=clock.now()).admit:
        replay.require(request)
    return await gateway.admit(request)
