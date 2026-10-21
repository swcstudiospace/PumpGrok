"""Tracer tests: deterministic ULIDs plus the audited LIVE_WRITE refusal (I3/I4)."""

from __future__ import annotations

import random
import re
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import LiveGateError, PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import RetryPolicy, ToolInput, ToolMeta, ToolOutput, ToolSpec, tool

ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


class _Clock:
    """Minimal Clock double: fixed wall time, no-op sleep/timeout."""

    def __init__(self, now: float) -> None:
        self._now = now

    def now(self) -> float:
        return self._now

    def monotonic(self) -> float:
        return self._now

    def utc_iso(self) -> str:
        return datetime.fromtimestamp(self._now, UTC).isoformat()

    async def sleep(self, seconds: float) -> None:
        return None

    @asynccontextmanager
    async def timeout(self, seconds: float) -> AsyncIterator[None]:
        yield None


class _In(ToolInput):
    q: str = "x"


class _Out(ToolOutput):
    answer: str = "y"


def _meta() -> ToolMeta:
    return ToolMeta(
        source="test",
        fetched_at=datetime.fromtimestamp(1469918176.385, UTC),
        freshness_s=0.0,
        correlation_id="01ARYZ6S41TSV4RRFF7Q3V9J6Q",
    )


def _read_spec() -> ToolSpec:
    return ToolSpec(
        name="market.price",
        description="Read-only price probe for tests.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        rate_limit_key="market",
        backend="test",
    )


def _live_spec() -> ToolSpec:
    return ToolSpec(
        name="exec.live_place",
        description="Live-write tool that must never resolve.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.LIVE_WRITE,
        timeout_s=5.0,
        rate_limit_key="exec",
        backend="test",
        idempotent=True,
    )


def test_retry_is_refused_until_wired() -> None:
    with pytest.raises(ValueError, match="retry is not applied yet"):
        ToolSpec(
            name="market.price",
            description="Read-only price probe for tests.",
            input_model=_In,
            output_model=_Out,
            side_effect=SideEffect.READ,
            timeout_s=5.0,
            retry=RetryPolicy(attempts=3),
            rate_limit_key="market",
            backend="test",
        )


async def _call(payload: Any) -> Any:  # pragma: no cover - replaced below
    raise AssertionError("unused")


def _registry(audits: list[GrantAudit], clock: _Clock) -> ToolRegistry:
    async def _allow(request: object, bot_id: str) -> bool:
        return True

    async def _live_call(payload: _In) -> _Out:
        return _Out(meta=_meta())

    async def _read_call(payload: _In) -> _Out:
        return _Out(meta=_meta())

    reg = ToolRegistry(clock=clock, audit_sink=audits.append, limits_checker=_allow)
    reg.register(tool(_read_spec())(_read_call))
    reg.register(tool(_live_spec())(_live_call))
    return reg


def _bot(bot_id: str, grants: list[ToolGrant], writes_to_exchange: bool = False) -> BotManifest:
    return BotManifest(
        id=bot_id,
        display=bot_id,
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=grants,
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
        writes_to_exchange=writes_to_exchange,
    )


def test_ulid_spec_vector_prefix() -> None:
    ms = 1469918176385
    factory = IdFactory(_Clock(ms / 1000), random.Random(0))
    first = factory.ulid()
    assert ULID_RE.match(first), first
    assert first.startswith("01ARYZ6S41"), first


def test_find_live_write_raises_for_every_caller_and_audits() -> None:
    audits: list[GrantAudit] = []
    reg = _registry(audits, _Clock(1469918176.385))
    factory = IdFactory(_Clock(1469918176.385), random.Random(1))
    readers = [
        _bot("bot-01-desk", [ToolGrant(name="market.price", side_effect=SideEffect.READ)]),
        _bot(
            "bot-04-sniper",
            [
                ToolGrant(name="market.price", side_effect=SideEffect.READ),
                ToolGrant(name="exec.live_place", side_effect=SideEffect.PAPER_WRITE),
            ],
            writes_to_exchange=True,
        ),
    ]
    for bot in readers:
        with bind_correlation(CorrelationId.new(factory)), pytest.raises(LiveGateError):
            reg.find("exec.live_place", max_side_effect=SideEffect.PAPER_WRITE, bot=bot)
    refusals = [a for a in audits if a.tool == "exec.live_place"]
    assert len(refusals) == 2
    assert all(a.allowed is False for a in refusals)
    assert all(a.reason == "live_write_never_resolvable" for a in refusals)


def test_find_read_for_granted_seat_resolves_and_audits_ok() -> None:
    audits: list[GrantAudit] = []
    reg = _registry(audits, _Clock(1469918176.385))
    factory = IdFactory(_Clock(1469918176.385), random.Random(2))
    bot = _bot("bot-01-desk", [ToolGrant(name="market.price", side_effect=SideEffect.READ)])
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("market.price", max_side_effect=SideEffect.READ, bot=bot)
    assert resolved.spec.name == "market.price"
    ok_rows = [a for a in audits if a.allowed]
    assert len(ok_rows) == 1
    assert ok_rows[0].reason == "ok"


def test_find_ungranted_tool_refuses_and_audits() -> None:
    audits: list[GrantAudit] = []
    reg = _registry(audits, _Clock(1469918176.385))
    factory = IdFactory(_Clock(1469918176.385), random.Random(3))
    with bind_correlation(CorrelationId.new(factory)), pytest.raises(PermissionDenied):
        reg.find(
            "market.price",
            max_side_effect=SideEffect.READ,
            bot=_bot("bot-03-x", []),
        )
    assert audits[-1].allowed is False


def test_tool_name_requires_multi_dot_namespace() -> None:
    with pytest.raises(ValidationError):
        ToolSpec(
            name="price",
            description="Missing namespace dot.",
            input_model=_In,
            output_model=_Out,
            side_effect=SideEffect.READ,
            timeout_s=5.0,
            rate_limit_key="market",
            backend="test",
        )
