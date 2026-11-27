"""Idle harness: 24 virtual hours of silence make zero Grok calls (EVT-12)."""

from __future__ import annotations

import asyncio

from pumpgrok.events.idle import CountingTransport, run_idle_grok_calls
from pumpgrok.grok import GatewayRequest


def test_counting_transport_counts_without_network() -> None:
    transport = CountingTransport()
    assert transport.calls == 0
    result = asyncio.run(
        transport(GatewayRequest(agent="seat", prompt="ping", consequence_id="c1"))
    )
    assert result == '{"ok": 1}'
    assert transport.calls == 1


def test_idle_harness_makes_no_gateway_calls() -> None:
    assert run_idle_grok_calls() == 0
