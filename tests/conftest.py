"""Offline by default: every test runs with outbound HTTP and websocket connects blocked.

Patches the class-specific transport methods, so `httpx.MockTransport` (a different
class) still serves recorded responses. Websocket connects are blocked at both the
modern path (`websockets.asyncio.client.connect`) and the top-level alias, plus the
names already bound in `pumpgrok.datafeed.transport` and `pumpgrok.engine.monitor`
(TEST-T08).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import websockets
import websockets.asyncio.client

import pumpgrok.datafeed.transport
import pumpgrok.engine.monitor
from harness import NetworkBlocked
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc

_MESSAGE = "outbound network is blocked in tests; use httpx.MockTransport"


def _blocked_sync(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlocked(_MESSAGE)


async def _blocked_async(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlocked(_MESSAGE)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked_sync)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _blocked_async)
    monkeypatch.setattr(websockets.asyncio.client, "connect", _blocked_sync)
    monkeypatch.setattr(websockets, "connect", _blocked_sync)
    monkeypatch.setattr(pumpgrok.engine.monitor, "connect", _blocked_sync)
    monkeypatch.setattr(pumpgrok.datafeed.transport, "connect", _blocked_sync)


@pytest.fixture
def roster_operator_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    """Grant each seat every tool its own roster lists, without writing ledger rows.

    The production gate reads grants from ConfigChanged rows in the paper ledger. Tests that
    assert that ledger exactly (for example an empty event list) cannot carry those rows, so
    they opt in here and the grant is supplied at the gate. The roster still decides: a seat
    never receives a tool its own roster does not list.
    """

    def allows(_self: oc.OperatorGrants, seat: str, tool: str) -> bool:
        if seat not in EXPECTED_SEAT_IDS:
            return False
        return tool in roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)

    monkeypatch.setattr(oc.OperatorGrants, "allows", allows)
