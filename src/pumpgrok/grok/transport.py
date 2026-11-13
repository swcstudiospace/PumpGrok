"""x.ai transport behind the gateway (GRK-05, GRK-06).

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
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import BaseModel

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.llm import GrokOps
from pumpgrok.grok.gateway import TRANSPORT_DEADLINE_S, GrokRequest
from pumpgrok.grok.sanitize import StrictParseError, parse_strict

__all__ = [
    "CHAT_COMPLETIONS_PATH",
    "MAX_RESPONSE_BYTES",
    "GrokTransportError",
    "MissingGrokKey",
    "XaiTransport",
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
        try:
            response = await self._client.post(
                self._endpoint,
                headers=headers,
                json=payload,
                timeout=TRANSPORT_DEADLINE_S,
            )
        except httpx.HTTPError:
            self._failed(request)
            raise GrokTransportError("x.ai request failed") from None

        if response.status_code != 200 or len(response.content) > MAX_RESPONSE_BYTES:
            self._failed(request)
            raise GrokTransportError("x.ai answer refused", status=response.status_code)

        try:
            body = response.json()
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

    def _failed(self, request: GrokRequest) -> None:
        if self._ops is not None:
            self._ops.record_failure(request.agent)


def _usage(body: Any) -> dict[str, Any] | None:
    usage = body.get("usage") if isinstance(body, dict) else None
    return usage if isinstance(usage, dict) else None
