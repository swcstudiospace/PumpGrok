"""Jupiter quote failure paths fail typed, never silently (QLT-06, 11-05 guard).

``get_quote`` keeps its informational contract: transport, HTTP-status and
decode failures return ``{"ok": False}`` and log the error class. Any other
exception is a programming error and must propagate, not be swallowed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
import pytest

from pumpgrok.tools.market.jupiter import get_quote

FAILED = {"ok": False, "error": "jupiter quote failed"}


def _client(fn: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(fn))


async def test_http_error_status_returns_ok_false_and_logs_error_class(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    with caplog.at_level(logging.WARNING, logger="pumpgrok.tools.market.jupiter"):
        result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result == FAILED
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("HTTPStatusError" in r.getMessage() for r in warnings)


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ConnectError("refused"),
        httpx.ReadTimeout("timed out"),
        httpx.RemoteProtocolError("bad frame"),
    ],
    ids=["connect", "timeout", "protocol"],
)
async def test_transport_errors_return_ok_false(exc: httpx.HTTPError) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result == FAILED


async def test_undecodable_body_returns_ok_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result == FAILED


async def test_non_object_json_returns_ok_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result == FAILED


async def test_route_plan_not_a_list_returns_ok_false() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"routePlan": "not-a-list"})

    result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result == FAILED


async def test_unexpected_error_propagates_instead_of_being_swallowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("programming bug")

    with pytest.raises(RuntimeError, match="programming bug"):
        await get_quote("A", "B", 1, 50, _client(handler))


async def test_overflowing_price_impact_is_malformed_not_raised() -> None:
    # A 400-digit JSON integer overflows float() with OverflowError, an
    # ArithmeticError. It is malformed data: the quote stays ok, ratio is None.
    body = b'{"priceImpact": ' + b"9" * 400 + b"}"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    result = await get_quote("A", "B", 1, 50, _client(handler))

    assert result["ok"] is True
    assert result["priceImpactRatio"] is None
