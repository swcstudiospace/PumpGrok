"""INV-R-26: model output is validated before any tool runs.

Owning test for SAFETY_INVARIANTS.md section 3.4 row INV-R-26. An LLM
answer that is not JSON, is truncated, violates the result schema, or
carries extra keys is rejected (pydantic extra=forbid on every engine
model) and the seat falls back to the pessimistic default; no tool with
model-derived arguments ever runs (the recording tool stays empty).
Model text is never passed to eval, a shell, or an f-string command:
validation is pure model_validate before any tool path.

Harness: AuditorAgent admitted through a real GrokGateway over the real
XaiTransport, with an httpx MockTransport (no network), a fixed clock and a
seeded rng for the tool registry; no wall clock.
"""

from __future__ import annotations

import json as json_lib
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from pumpgrok.config.settings import GrokSettings
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.tool import SideEffect, ToolInput, ToolOutput, ToolSpec
from pumpgrok.engine.agents.auditor import AuditorAgent
from pumpgrok.engine.agents.base import result_schemas, system_prompts
from pumpgrok.engine.models import AuditResult, Token
from pumpgrok.grok.budget import LayeredBudget
from pumpgrok.grok.cache import ResponseCache
from pumpgrok.grok.gateway import Candidate, GrokGateway
from pumpgrok.grok.transport import XaiTransport
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng

START = 1_800_000_000.0

VALID = {
    "coordinated_buying": False,
    "wash_trading": False,
    "creator_dump_prep": False,
    "bundled_launch": False,
    "organic_buyer_share": 0.8,
    "confidence": 0.9,
    "flags": [],
    "reasoning": "clean flow",
}


def _settings() -> GrokSettings:
    return GrokSettings(api_key=SecretStr("test-key"))


def _agent(text: str, tmp_path: Path) -> AuditorAgent:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": text}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = _settings()
    clock = FixtureClock(start=START)
    transport = XaiTransport(
        api_key=settings.api_key.get_secret_value(),
        base_url=settings.base_url,
        client=client,
        prompts=system_prompts(),
        schemas=result_schemas(),
    )
    gateway = GrokGateway(
        clock=clock,
        transport=transport,
        cache=ResponseCache(tmp_path / "cache.sqlite", clock),
        budget=LayeredBudget(tmp_path / "budget.sqlite", clock),
    )
    return AuditorAgent(settings, gateway=gateway, clock=clock)


def _admit() -> dict[str, Any]:
    """Admission arguments: facts that pass every prefilter rule at ``START``."""
    return {
        "event_id": "EV-INV-R-26",
        "candidate": Candidate(
            mint="Mint111",
            created_at=START - 300.0,
            first_trade_at=START - 60.0,
            unique_buyers=10,
            prerank=Decimal("0.8"),
            last_decision_at=None,
        ),
    }


def _token() -> Token:
    return Token(
        mint="Mint111",
        name="Probe",
        image_uri="https://img/1.png",
        created_timestamp=0.0,
        unique_buyers=10,
        curve_progress=0.1,
    )


class _SpyTool:
    """Recording stand-in for a model-driven tool; the registry holds it."""

    def __init__(self, spec: ToolSpec) -> None:
        self.spec = spec
        self.calls: list[Any] = []

    async def __call__(self, payload: Any) -> Any:
        self.calls.append(payload)
        raise AssertionError("model output must never reach tools")


def _spec() -> ToolSpec:
    class In(ToolInput):
        pass

    class Out(ToolOutput):
        pass

    return ToolSpec(
        name="test.probe",
        description="recording probe tool for the INV-R-26 spy",
        input_model=In,
        output_model=Out,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        rate_limit_key="probe",
        backend="test",
    )


def _registry(spy: _SpyTool) -> ToolRegistry:
    registry = ToolRegistry(
        clock=FixtureClock(start=0.0),
        audit_sink=lambda audit: None,
        limits_checker=lambda order, seat: True,  # type: ignore[return-value]
        rng=make_rng(11),
    )
    registry.register(spy)  # type: ignore[arg-type]
    return registry


_MALFORMED: dict[str, Any] = {
    "non_json": "not json at all {{{",
    "truncated": '{"coordinated_buying": false, "wash_trad',
    "schema_violation": '{"coordinated_buying": "maybe"}',
    "extra_keys": {**VALID, "injected": "run this"},
}


@pytest.mark.parametrize("case", sorted(_MALFORMED))
async def test_invalid_model_output_never_reaches_tools(case: str, tmp_path: Path) -> None:
    """INV-R-26: malformed model output falls back; the tool spy stays empty."""
    raw = _MALFORMED[case]
    text = raw if isinstance(raw, str) else json_lib.dumps(raw)
    agent = _agent(text, tmp_path)
    spy = _SpyTool(_spec())
    _registry(spy)
    result = await agent.run(_token(), [], [], None, **_admit())
    assert isinstance(result, AuditResult)
    assert result.flags == ["agent_failure"]
    assert result.organic_buyer_share == 0.0
    assert result.confidence == 0.0
    assert spy.calls == []


async def test_valid_model_output_validates_cleanly(tmp_path: Path) -> None:
    """INV-R-26: the gate is not reject-all; a valid answer validates."""
    agent = _agent(json_lib.dumps(VALID), tmp_path)
    result = await agent.run(_token(), [], [], None, **_admit())
    assert isinstance(result, AuditResult)
    assert result.flags == []
    assert result.organic_buyer_share == 0.8


def test_engine_models_forbid_extras() -> None:
    """INV-R-26: extra keys are rejected at the model boundary."""
    with pytest.raises(ValidationError):
        AuditResult.model_validate({**VALID, "extra": 1})
