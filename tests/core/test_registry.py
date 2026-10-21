"""Tracer tests: deterministic ULIDs plus the audited LIVE_WRITE refusal (I3/I4)."""

from __future__ import annotations

import hashlib
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


def test_read_retry_policy_validates() -> None:
    ToolSpec(  # READ tools may declare j4/j5/j8 (TOOL-002, TOOL-008)
        name="market.price",
        description="Read-only price probe with retry.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        retry=RetryPolicy(attempts=3, base_s=0.5, max_s=4.0),
        rate_limit_key="market",
        backend="test",
    )


def test_write_retry_is_refused() -> None:
    # Rule: retry with attempts > 1 is READ-only; writes keep attempts=1
    # (catalog: exec.place "retry none") even after the registry wires retry.
    with pytest.raises(ValueError, match="READ-only"):
        ToolSpec(
            name="exec.place",
            description="Paper-write place must not declare retry.",
            input_model=_In,
            output_model=_Out,
            side_effect=SideEffect.PAPER_WRITE,
            timeout_s=20.0,
            retry=RetryPolicy(attempts=2),
            rate_limit_key="exec",
            requires_approval=True,
            idempotent=True,
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


def _quote_spec() -> ToolSpec:
    return ToolSpec(
        name="exec.quote",
        description="Read-only quote probe sharing the exec namespace.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        rate_limit_key="jupiter",
        backend="test",
    )


def _cancel_spec() -> ToolSpec:
    return ToolSpec(
        name="exec.cancel",
        description="Paper-write cancel probe sorting before the quote.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.PAPER_WRITE,
        timeout_s=10.0,
        rate_limit_key="exec",
        requires_approval=True,
        idempotent=True,
        backend="test",
    )


def test_prefix_find_skips_tools_above_requested_max() -> None:
    audits: list[GrantAudit] = []
    clock = _Clock(1469918176.385)

    async def _allow(request: object, bot_id: str) -> bool:
        return True

    async def _read_call(payload: _In) -> _Out:
        return _Out(meta=_meta())

    async def _write_call(payload: _In) -> _Out:
        return _Out(meta=_meta())

    reg = ToolRegistry(clock=clock, audit_sink=audits.append, limits_checker=_allow)
    reg.register(tool(_cancel_spec())(_write_call))
    reg.register(tool(_quote_spec())(_read_call))
    bot = _bot(
        "bot-04-sniper",
        [
            ToolGrant(name="exec.cancel", side_effect=SideEffect.PAPER_WRITE),
            ToolGrant(name="exec.quote", side_effect=SideEffect.READ),
        ],
        writes_to_exchange=True,
    )
    factory = IdFactory(clock, random.Random(4))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("exec", max_side_effect=SideEffect.READ, bot=bot)
    assert resolved.spec.name == "exec.quote"


def test_exec_place_key_excludes_tool_and_bot() -> None:
    from pumpgrok.core.idempotency import canonical_json, exec_place_key

    ticket, side, decision = "SOL-20260101-001", "buy", "01ARYZ6S41TSV4RRFF7Q3V9J6Q"
    key = exec_place_key(ticket, side, decision)
    assert key == exec_place_key(ticket, side, decision)
    assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)
    assert exec_place_key(ticket, "sell", decision) != key
    assert exec_place_key("SOL-20260101-002", side, decision) != key
    body = canonical_json({"ticket_id": ticket, "side": side, "decision_id": decision})
    assert key == hashlib.sha256(body.encode()).hexdigest()[:32]


def test_exec_cancel_key_derives_from_order_only() -> None:
    from pumpgrok.core.idempotency import exec_cancel_key

    key = exec_cancel_key("order-1")
    assert key == exec_cancel_key("order-1")
    assert len(key) == 32 and all(c in "0123456789abcdef" for c in key)
    assert exec_cancel_key("order-2") != key


def test_register_all_duplicate_name_raises() -> None:
    audits: list[GrantAudit] = []
    clock = _Clock(1469918176.385)

    async def _allow(request: object, bot_id: str) -> bool:
        return True

    async def _read_call(payload: _In) -> _Out:
        return _Out(meta=_meta())

    reg = ToolRegistry(clock=clock, audit_sink=audits.append, limits_checker=_allow)
    probe = tool(_read_spec())(_read_call)
    with pytest.raises(ValueError, match="duplicate tool"):
        reg.register_all([probe, probe])
