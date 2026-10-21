"""Money typing boundary (TOOL-008, R28) and the registry tracer (wave 1).

The tracer proves the composition-root slice before any catalog tool lands:
`build_registry()` resolves one READ probe through `find()` with
`max_side_effect=READ`, `_wrap` executes it under `clock.timeout`, the
fail-closed limits checker refuses approval-gated calls, and every attempt
writes an audit row (I4).
"""

from __future__ import annotations

import asyncio
import random
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest
from pydantic import ValidationError

from pumpgrok.cli import UsageError, _size_sol, size_sol_to_lamports
from pumpgrok.core.adapter import Side
from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import DataBlind, DataStale, PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import (
    ToolInput,
    ToolMeta,
    ToolOutput,
    ToolSpec,
    UpstreamModel,
    parse_upstream,
    tool,
)
from pumpgrok.replay.clock import FixtureClock, WallClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.tools import build_registry

START = 1469918176.385
ULID = "01ARYZ6S41TSV4RRFF7Q3V9J6Q"


class _ProbeIn(ToolInput):
    query: str = "ping"


class _ProbeOut(ToolOutput):
    answer: str = "pong"


class _PlaceIn(ToolInput):
    """Approval-gated write input mirroring OrderRequest fields (fail-closed probe)."""

    ticket_id: str = "SOL-20260101-001"
    mint: str = "M" * 32
    side: Side = Side.BUY
    decision_id: str = ULID
    size_lamports: int = 1000
    max_slippage_bps: int = 100
    approval_id: str = f"apr-{ULID}"


def _meta() -> ToolMeta:
    return ToolMeta(
        source="test",
        fetched_at=datetime.fromtimestamp(START, UTC),
        freshness_s=0.0,
        correlation_id=ULID,
    )


def _probe_spec() -> ToolSpec:
    return ToolSpec(
        name="desk.probe",
        description="Tracer probe: a single READ tool proving the registry slice.",
        input_model=_ProbeIn,
        output_model=_ProbeOut,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        rate_limit_key="desk",
        backend="test",
    )


def _place_spec() -> ToolSpec:
    return ToolSpec(
        name="exec.probe",
        description="Tracer probe: an approval-gated write proving fail-closed limits.",
        input_model=_PlaceIn,
        output_model=_ProbeOut,
        side_effect=SideEffect.PAPER_WRITE,
        timeout_s=10.0,
        rate_limit_key="exec",
        requires_approval=True,
        idempotent=True,
        backend="test",
    )


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


async def test_tracer_read_probe_resolves_and_runs() -> None:
    clock = FixtureClock(start=START)
    reg, audits = build_registry(clock=clock, rng=random.Random(11))

    async def _probe(payload: _ProbeIn) -> _ProbeOut:
        return _ProbeOut(meta=_meta(), answer="pong")

    reg.register(tool(_probe_spec())(_probe))
    bot = _bot("bot-00-chief", [ToolGrant(name="desk.probe", side_effect=SideEffect.READ)])
    factory = IdFactory(clock, random.Random(12))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("desk.probe", max_side_effect=SideEffect.READ, bot=bot)
        out = await resolved(_ProbeIn())
    assert out.answer == "pong"
    ok_rows = [a for a in audits if a.tool == "desk.probe" and a.allowed]
    assert len(ok_rows) == 1
    assert ok_rows[0].reason == "ok"


async def test_tracer_limits_checker_refuses_by_default() -> None:
    clock = FixtureClock(start=START)
    reg, audits = build_registry(clock=clock, rng=random.Random(13))

    async def _place(payload: _PlaceIn) -> _ProbeOut:  # pragma: no cover - never reached
        raise AssertionError("fail-closed checker must refuse before the tool runs")

    reg.register(tool(_place_spec())(_place))
    bot = _bot(
        "bot-04-sniper",
        [ToolGrant(name="exec.probe", side_effect=SideEffect.PAPER_WRITE)],
        writes_to_exchange=True,
    )
    factory = IdFactory(clock, random.Random(14))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("exec.probe", max_side_effect=SideEffect.PAPER_WRITE, bot=bot)
        with pytest.raises(PermissionDenied, match="RiskEngine.check refused"):
            await resolved(_PlaceIn())
    assert any(a.tool == "exec.probe" and a.allowed for a in audits)


async def test_tracer_wrap_applies_clock_timeout() -> None:
    reg, _ = build_registry(clock=WallClock(), rng=make_rng(15))

    async def _hang(payload: _ProbeIn) -> _ProbeOut:  # pragma: no cover - cancelled
        await asyncio.sleep(5.0)
        raise AssertionError("unreachable")

    spec = _probe_spec().model_copy(update={"timeout_s": 0.05})
    reg.register(tool(spec)(_hang))
    bot = _bot("bot-00-chief", [ToolGrant(name="desk.probe", side_effect=SideEffect.READ)])
    factory = IdFactory(WallClock(), random.Random(16))
    with bind_correlation(CorrelationId.new(factory)):
        resolved = reg.find("desk.probe", max_side_effect=SideEffect.READ, bot=bot)
        with pytest.raises(TimeoutError):
            await resolved(_ProbeIn())


class _MoneyOut(ToolOutput):
    price: Decimal


class _UpstreamPrice(UpstreamModel):
    price: Decimal


def test_canonical_json_rejects_float_leaves() -> None:
    from pumpgrok.core.idempotency import canonical_json

    assert canonical_json({"price": Decimal("1.5")}) == '{"price":"1.5"}'
    with pytest.raises(TypeError, match="float leaves are forbidden"):
        canonical_json({"price": 1.5})
    with pytest.raises(TypeError, match="float leaves are forbidden"):
        canonical_json({"nested": {"price": 1.5}})


def test_decimal_serializes_as_json_string() -> None:
    dumped = _MoneyOut(meta=_meta(), price=Decimal("1.5")).model_dump(mode="json")
    assert dumped["price"] == "1.5"


def test_tool_envelopes_forbid_extra() -> None:
    assert ToolInput.model_config.get("extra") == "forbid"
    assert ToolOutput.model_config.get("extra") == "forbid"
    assert UpstreamModel.model_config.get("extra") == "ignore"
    with pytest.raises(ValidationError):
        _ProbeIn(query="ping", unknown_field="nope")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _ProbeOut(meta=_meta(), answer="pong", unknown_field="nope")  # type: ignore[call-arg]


def test_upstream_model_ignores_extra_and_maps_errors() -> None:
    parsed = parse_upstream(_UpstreamPrice, {"price": "1.5", "venue_noise": 123})
    assert parsed.price == Decimal("1.5")
    with pytest.raises(DataStale, match="unparsable"):
        parse_upstream(_UpstreamPrice, {"price": "not-a-number"})
    with pytest.raises(DataBlind, match="no last-good value"):
        parse_upstream(_UpstreamPrice, {"price": "not-a-number"}, blind=True)
    with pytest.raises(DataStale):
        parse_upstream(_UpstreamPrice, {"price": None})


def test_cli_size_sol_conversions() -> None:
    assert _size_sol("0.5") == Decimal("0.5")
    assert size_sol_to_lamports(Decimal("0.5")) == 500_000_000
    assert size_sol_to_lamports(Decimal("0.0000000015")) == 2  # ROUND_HALF_UP
    assert size_sol_to_lamports(_size_sol("1")) == 1_000_000_000
    for bad in ("abc", "-1", "0", "NaN", "Infinity"):
        with pytest.raises(UsageError):
            _size_sol(bad)
