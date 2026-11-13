"""Grok agent base: one prompt, one response schema, one gateway admission.

Every model call from the four agents goes through ``GrokGateway.admit``. The
gateway owns the prefilter, the sanitizer, the cache, in-flight coalescing,
the layered budget, the breaker and the call deadline; the x.ai transport owns
the wire. This module holds no HTTP client, no API key and no retry loop.
``GrokAgent`` requires a gateway at construction, so an agent has no path to
the network that bypasses admission.

Prompt and response schema are code constants. The transport resolves a
request's system prompt by ``prompt_sha`` (``system_prompts()``) and its
response schema by ``schema`` (``result_schemas()``), so both keys are the
sha256 of the constant. Untrusted model output crosses here: it is parsed as
data into pydantic models, never executed.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from pumpgrok.config.settings import GrokSettings
from pumpgrok.engine.models import Token
from pumpgrok.grok.gateway import Candidate, GrokGateway, GrokRequest
from pumpgrok.replay.clock import Clock

log = logging.getLogger(__name__)

JSON_ONLY = (
    "Reply with a single JSON object only, no markdown fences, no commentary. "
    "Every required key must be present."
)

# Every concrete agent registers itself here on definition, so the prompt and
# schema registries cover the full set without an import cycle.
_AGENT_TYPES: dict[str, type[GrokAgent]] = {}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _schema_sha(model: type[BaseModel]) -> str:
    canonical = json.dumps(model.model_json_schema(), sort_keys=True, separators=(",", ":"))
    return _sha256(canonical)


def system_prompts() -> dict[str, str]:
    """System prompt text keyed by ``prompt_sha``, for every registered agent."""
    return {_sha256(cls.prompt): cls.prompt for cls in _AGENT_TYPES.values()}


def result_schemas() -> dict[str, type[BaseModel]]:
    """Response model keyed by its schema sha, for every registered agent."""
    return {_schema_sha(cls.result_model): cls.result_model for cls in _AGENT_TYPES.values()}


def gateway_candidate(
    token: Token,
    *,
    prerank: Decimal,
    first_trade_at: float,
    last_decision_at: float | None = None,
) -> Candidate:
    """Admission facts the gateway prefilter reads, from the token and the caller.

    The token supplies the creation time and the buyer count. The caller supplies
    the rule prerank, the first trade time and the mint's last decision time,
    which no agent holds. Missing buyer evidence counts as zero buyers, so the
    prefilter fails closed before any spend.
    """
    return Candidate(
        mint=token.mint,
        created_at=token.created_timestamp,
        first_trade_at=first_trade_at,
        unique_buyers=0 if token.unique_buyers is None else token.unique_buyers,
        prerank=prerank,
        last_decision_at=last_decision_at,
    )


class GrokAgent:
    """One agent: one system prompt plus one pydantic response schema."""

    name: ClassVar[str] = "agent"
    prompt: ClassVar[str] = ""
    result_model: ClassVar[type[BaseModel]] = BaseModel
    use_checker_model: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _AGENT_TYPES[cls.name] = cls

    @property
    def model(self) -> str:
        """Strong model for the checker, fast model for every other agent."""
        if self.use_checker_model:
            return self._grok.strong_model
        return self._grok.fast_model

    @property
    def prompt_sha(self) -> str:
        return _sha256(self.prompt)

    @property
    def schema_sha(self) -> str:
        return _schema_sha(self.result_model)

    def __init__(self, grok: GrokSettings, *, gateway: GrokGateway, clock: Clock) -> None:
        self._grok = grok
        self._gateway = gateway
        self._clock = clock

    def build_user_message(self, *args: Any, **kwargs: Any) -> str:
        """Assemble the user message. Heirs map their inputs to JSON here."""
        raise NotImplementedError

    def fallback(self, reason: str) -> Any:
        """Pessimistic result. Heirs must return the worst case, never raise."""
        raise NotImplementedError

    async def run(
        self,
        *args: Any,
        event_id: str,
        candidate: Candidate,
        **kwargs: Any,
    ) -> Any:
        """Build the prompt, admit it through the gateway, parse the answer.

        ``event_id`` is the causation id and ``candidate`` carries the facts the
        gateway prefilter reads. Never raises on a model or gateway failure:
        every refusal becomes this agent's pessimistic fallback, with the
        refusal reason as its explanation.
        """
        try:
            message = self.build_user_message(*args, **kwargs)
        except Exception as exc:
            log.warning("[%s] could not build prompt: %s", self.name, exc)
            return self.fallback(f"prompt_error: {exc}")

        request = GrokRequest(
            agent=self.name,
            event_id=event_id,
            model=self.model,
            prompt_sha=self.prompt_sha,
            schema=self.schema_sha,
            input={},
            text=message,
            candidate=candidate,
        )
        outcome = await self._gateway.admit(request)
        if outcome.response is None:
            reason = outcome.reason or outcome.status
            log.warning("[%s] no answer: %s", self.name, reason)
            return self.fallback(reason)

        try:
            data = extract_json(outcome.response)
        except ValueError as exc:
            log.warning("[%s] answer is not JSON: %s", self.name, exc)
            return self.fallback(f"parse_error: {exc}")

        try:
            return self.result_model.model_validate(data)
        except ValidationError as exc:
            log.warning("[%s] answer violates schema: %s", self.name, exc)
            return self.fallback(f"schema_error: {exc.error_count()} fields")


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
