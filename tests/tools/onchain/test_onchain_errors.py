"""Onchain check failures are typed (QLT-06).

RPC failures and malformed payloads return ``ok: False`` with the cause; any other
exception propagates instead of being swallowed as a generic failure string.
"""

from __future__ import annotations

import random
from typing import Any

import httpx
import pytest

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain.authorities import check_mint
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.rpc import RpcClient

MINT = "So11111111111111111111111111111111111111112"
ENDPOINT = "https://rpc.invalid"


def _rpc(handler: Any) -> RpcClient:
    return RpcClient(
        [ENDPOINT],
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        FixtureClock(),
        rng=random.Random(7),
        max_attempts_per_endpoint=1,
    )


def _result(value: Any) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"value": value}})

    return _rpc(handler)


def _http_status(status: int) -> RpcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "nope"})

    return _rpc(handler)


def _bad_body() -> RpcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    return _rpc(handler)


def _raising(rpc: RpcClient) -> RpcClient:
    async def boom(method: str, params: list[Any]) -> Any:
        raise RuntimeError("unexpected")

    rpc.call = boom  # type: ignore[method-assign]
    return rpc


async def test_authority_rpc_error_is_typed_false_without_url() -> None:
    result = await check_mint(MINT, _http_status(400))
    assert result["ok"] is False
    assert result["mint"] == MINT
    assert result["error"] == "rpc failed method=getAccountInfo endpoints=1"
    assert "rpc.invalid" not in str(result)


async def test_authority_bad_body_reports_data_stale_reason() -> None:
    result = await check_mint(MINT, _bad_body())
    assert result == {
        "ok": False,
        "error": "rpc bad body method=getAccountInfo endpoints=1",
        "mint": MINT,
    }


async def test_authority_malformed_value_is_typed_false() -> None:
    result = await check_mint(MINT, _result("garbage"))
    assert result == {"ok": False, "error": "authority check failed", "mint": MINT}


async def test_authority_unexpected_error_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        await check_mint(MINT, _raising(_http_status(200)))


async def test_holder_rpc_error_is_typed_false_without_url() -> None:
    result = await holder_snapshot(MINT, _http_status(400))
    assert result["ok"] is False
    assert result["mint"] == MINT
    assert result["error"] == "rpc failed method=getTokenLargestAccounts endpoints=1"
    assert "rpc.invalid" not in str(result)


async def test_holder_bad_body_reports_data_stale_reason() -> None:
    result = await holder_snapshot(MINT, _bad_body())
    assert result == {
        "ok": False,
        "error": "rpc bad body method=getTokenLargestAccounts endpoints=1",
        "mint": MINT,
    }


async def test_holder_malformed_item_is_typed_false() -> None:
    result = await holder_snapshot(MINT, _result([42]))
    assert result == {"ok": False, "error": "holder check failed", "mint": MINT}


async def test_holder_unexpected_error_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        await holder_snapshot(MINT, _raising(_http_status(200)))
