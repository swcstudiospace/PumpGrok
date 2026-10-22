"""Span timing for every tool call (OBS-003, INV-S-13)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from pumpgrok.core.bot import BotManifest, ToolGrant
from pumpgrok.core.errors import PumpgrokError
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.registry import ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import ToolInput, ToolMeta, ToolOutput, ToolSpec, tool
from pumpgrok.logging import setup_logging
from pumpgrok.logging.spans import bind_clock, current_clock, span
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng


@pytest.fixture
def clock() -> FixtureClock:
    return FixtureClock(start=1_000.0)


@pytest.fixture
def root_handlers() -> Iterator[None]:
    """Restore the root logger after each test."""
    root = logging.getLogger()
    saved = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)
    root.setLevel(level)


class _Capture(logging.Handler):
    """Collect records from the spans logger regardless of root level."""

    def __init__(self, records: list[logging.LogRecord]) -> None:
        super().__init__()
        self._records = records

    def emit(self, record: logging.LogRecord) -> None:
        self._records.append(record)


@contextmanager
def _captured(records: list[logging.LogRecord]) -> Iterator[None]:
    """Attach a capture handler to the spans logger at INFO level."""
    logger = logging.getLogger("pumpgrok.spans")
    handler = _Capture(records)
    level = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def test_span_duration_equals_clock_delta(clock: FixtureClock) -> None:
    records: list[logging.LogRecord] = []
    with _captured(records):
        with bind_clock(clock):
            with span("probe", seat="bot-00-chief"):
                clock.advance_to(1_000.0 + 2.5)
    assert len(records) == 1
    record = records[0]
    assert getattr(record, "event") == "span"
    assert getattr(record, "duration_ms") == pytest.approx(2500.0)
    assert getattr(record, "span") == "probe"


async def test_span_supports_async_with(clock: FixtureClock) -> None:
    records: list[logging.LogRecord] = []
    with _captured(records):
        with bind_clock(clock):
            async with span("probe"):
                # FixtureClock.sleep only fires when virtual time advances;
                # move it synchronously instead of awaiting a timer.
                clock.advance_to(clock.now() + 1.5)
    assert len(records) == 1
    assert getattr(records[0], "duration_ms") == pytest.approx(1500.0)


def test_spans_nest_with_parent_and_depth(clock: FixtureClock) -> None:
    records: list[logging.LogRecord] = []
    with _captured(records):
        with bind_clock(clock):
            with span("outer"):
                with span("inner"):
                    pass
    seen = [
        (getattr(record, "span"), getattr(record, "parent"), getattr(record, "depth"))
        for record in records
    ]
    assert seen == [("inner", "outer", 2), ("outer", None, 1)]


def test_span_without_bound_clock_raises() -> None:
    with pytest.raises(PumpgrokError, match="no span clock bound"):
        with span("probe"):
            pass  # pragma: no cover


def test_current_clock_returns_bound_clock(clock: FixtureClock) -> None:
    with bind_clock(clock):
        assert current_clock() is clock


def test_span_fields_pass_through_redaction_filter(
    clock: FixtureClock, root_handlers: None
) -> None:
    buffer = io.StringIO()
    setup_logging(mode="paper", profile="paper", environ={}, stream=buffer)
    with bind_clock(clock):
        with span("probe", api_key="test-value-not-a-secret"):
            pass
    lines = [line for line in buffer.getvalue().splitlines() if line]
    assert len(lines) == 1
    body = json.loads(lines[0])
    assert body["event"] == "span"
    assert body["data"]["api_key"] == "[redacted]"


class _In(ToolInput):
    q: str = "x"


class _Out(ToolOutput):
    answer: str = "y"


def _meta() -> ToolMeta:
    return ToolMeta(
        source="test",
        fetched_at=datetime.fromtimestamp(1_000.0, UTC),
        freshness_s=0.0,
        correlation_id="01ARYZ6S41TSV4RRFF7Q3V9J6Q",
    )


async def test_registry_tool_call_emits_one_span(clock: FixtureClock) -> None:
    async def _allow(request: object, bot_id: str) -> bool:
        return True

    async def _read_call(payload: _In) -> _Out:
        # Move virtual time synchronously: FixtureClock.sleep only fires
        # when something else advances the clock, so awaiting it deadlocks.
        clock.advance_to(clock.now() + 0.25)
        return _Out(meta=_meta())

    reg = ToolRegistry(clock=clock, audit_sink=lambda audit: None, limits_checker=_allow)
    reg.register(
        tool(
            ToolSpec(
                name="market.price",
                description="Read-only price probe for tests.",
                input_model=_In,
                output_model=_Out,
                side_effect=SideEffect.READ,
                timeout_s=5.0,
                rate_limit_key="market",
                backend="test",
            )
        )(_read_call)
    )
    bot = BotManifest(
        id="bot-00-chief",
        display="bot-00-chief",
        channel="DM",
        purpose="test seat",
        inputs=[],
        outputs=[],
        skills=[],
        allowed_tools=[ToolGrant(name="market.price", side_effect=SideEffect.READ)],
        risk_budget={},
        forbidden=[],
        fail_safe="halt",
        schedule=[],
        escalation=[],
        owned_paths=[],
        receipts_dir="var/receipts",
        prompt_source="test",
        writes_to_exchange=False,
    )
    records: list[logging.LogRecord] = []
    with _captured(records):
        factory = IdFactory(clock, make_rng(7))
        with bind_correlation(CorrelationId.new(factory)):
            found = reg.find("market.price", max_side_effect=SideEffect.READ, bot=bot)
            await found(_In())
    spans = [r for r in records if getattr(r, "event", None) == "span"]
    assert len(spans) == 1
    assert getattr(spans[0], "span") == "market.price"
    assert getattr(spans[0], "duration_ms") == pytest.approx(250.0)
    assert getattr(spans[0], "correlation_id", "").endswith(".1")
