"""Event-mode metric collectors: handler, DLQ and transport observers."""

from __future__ import annotations

import asyncio
import contextlib

from pumpgrok.events.models import Event, EventKind
from pumpgrok.supervisor.metrics import Metrics
from pumpgrok.supervisor.metrics_events import (
    assert_nine_families_unchanged,
    build_event_registry,
)

MINT = "So11111111111111111111111111111111111111112"


def _event() -> Event:
    return Event(
        kind=EventKind.trade,
        entity_id=MINT,
        payload={},
        occurred_at="2026-01-01T00:00:00Z",
    )


def _exposition() -> str:
    return Metrics(event_mode=True).exposition().decode()


def test_handler_observer_counts_delivered_and_failed() -> None:
    metrics = Metrics(event_mode=True)
    collectors = metrics.events
    assert collectors is not None

    async def _ok(event: Event) -> None: ...

    async def _bad(event: Event) -> None:
        raise ValueError("boom")

    asyncio.run(collectors.observe_handler(_ok)(_event()))
    try:
        asyncio.run(collectors.observe_handler(_bad)(_event()))
    except ValueError:
        pass
    else:
        raise AssertionError("observer swallowed the handler error")
    exposition = metrics.exposition().decode()
    assert 'pumpgrok_events_total{kind="trade",outcome="delivered"} 1.0' in exposition
    assert 'pumpgrok_events_total{kind="trade",outcome="failed"} 1.0' in exposition


def test_dlq_observer_counts_sync_and_async_handoffs() -> None:
    metrics = Metrics(event_mode=True)
    collectors = metrics.events
    assert collectors is not None

    collectors.observe_dlq(lambda event: None)(_event())

    async def _async_dlq(event: Event) -> None: ...

    asyncio.run(collectors.observe_dlq(_async_dlq)(_event()))
    exposition = metrics.exposition().decode()
    assert 'pumpgrok_event_dlq_total{kind="trade"} 2.0' in exposition


def test_transport_observer_counts_ok_and_error() -> None:
    metrics = Metrics(event_mode=True)
    collectors = metrics.events
    assert collectors is not None

    async def _ok(request: object, text: str) -> str:
        return "resp"

    async def _bad(request: object, text: str) -> str:
        raise RuntimeError("transport down")

    request = SimpleNamespace(agent="bot-01-scout")
    wrapped_ok = collectors.observe_transport(_ok)  # type: ignore[arg-type]
    wrapped_bad = collectors.observe_transport(_bad)  # type: ignore[arg-type]
    assert asyncio.run(wrapped_ok(request, "x")) == "resp"  # type: ignore[arg-type]
    with contextlib.suppress(RuntimeError):
        asyncio.run(wrapped_bad(request, "x"))  # type: ignore[arg-type]
    exposition = metrics.exposition().decode()
    assert 'pumpgrok_grok_calls_total{agent="bot-01-scout",outcome="ok"} 1.0' in exposition
    assert 'pumpgrok_grok_calls_total{agent="bot-01-scout",outcome="error"} 1.0' in exposition


def test_build_event_registry_only_in_event_mode() -> None:
    assert build_event_registry("cadence") is None
    registry = build_event_registry("event")
    assert registry is not None
    assert assert_nine_families_unchanged() is True
    assert registry is not None


def test_collectors_share_the_metrics_registry() -> None:
    metrics = Metrics(event_mode=True)
    assert metrics.events is not None
    assert metrics.events.registry is metrics.registry
    assert _exposition()  # fresh collectors still render
