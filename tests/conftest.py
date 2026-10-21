"""Offline by default: every test runs with outbound HTTP and websocket connects blocked.

Patches the class-specific transport methods, so `httpx.MockTransport` (a different
class) still serves recorded responses. Websocket connects are blocked at both the
modern path (`websockets.asyncio.client.connect`) and the top-level alias.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import websockets
import websockets.asyncio.client

from harness import NetworkBlocked

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
