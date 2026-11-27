"""Onchain check failures are typed (QLT-06).

RPC failures and malformed payloads return ``ok: False`` with the cause; any other
exception propagates instead of being swallowed as a generic failure string.
"""

from __future__ import annotations

import json
import random
from typing import Any

import httpx
import pytest

from pumpgrok.core.errors import DataStale
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools.onchain.authorities import check_mint
from pumpgrok.tools.onchain.holders import holder_snapshot
from pumpgrok.tools.onchain.large_transfers import LargeTransfersIn, run_large_transfers
from pumpgrok.tools.onchain.priority_fee import estimate_priority_fee
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


async def test_holder_huge_integer_amount_is_typed_false() -> None:
    """float() on a 400-digit integer raises OverflowError; it must fail typed, not escape."""
    result = await holder_snapshot(MINT, _result([{"address": "Holder", "uiAmount": 10**400}]))
    assert result == {"ok": False, "error": "holder check failed", "mint": MINT}


async def test_holder_unexpected_error_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        await holder_snapshot(MINT, _raising(_http_status(200)))


async def test_holder_null_ui_amount_is_typed_false() -> None:
    """A null amount is missing data, not a zero holder; shares must not be understated."""
    result = await holder_snapshot(MINT, _result([{"address": "Holder", "uiAmount": None}]))
    assert result == {"ok": False, "error": "holder check failed", "mint": MINT}


async def test_priority_fee_rpc_error_is_typed_false() -> None:
    result = await estimate_priority_fee(_http_status(400))
    assert result == {
        "ok": False,
        "error": "rpc failed method=getRecentPrioritizationFees endpoints=1",
    }


async def test_priority_fee_unexpected_error_propagates() -> None:
    with pytest.raises(RuntimeError, match="unexpected"):
        await estimate_priority_fee(_raising(_http_status(200)))


def _large_transfers_rpc(failing: str) -> RpcClient:
    """Supply and signatures succeed; the ``failing`` method answers with an RPC error."""
    answers: dict[str, Any] = {
        "getTokenSupply": {"value": {"amount": "100000000", "decimals": 6}},
        "getSignaturesForAddress": [{"signature": "s1", "blockTime": 1}],
        "getTransaction": None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        method = json.loads(request.content.decode("utf-8"))["method"]
        if method == failing:
            body = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}}
            return httpx.Response(200, json=body)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": answers[method]})

    return _rpc(handler)


async def test_large_transfers_signature_rpc_error_is_data_stale() -> None:
    """A failed wallet read must not come back as a complete scan of the other wallets."""
    rpc = _large_transfers_rpc("getSignaturesForAddress")
    with pytest.raises(DataStale):
        await run_large_transfers(LargeTransfersIn(mint=MINT, wallets=["7" * 44]), rpc)


async def test_large_transfers_transaction_rpc_error_is_data_stale() -> None:
    rpc = _large_transfers_rpc("getTransaction")
    with pytest.raises(DataStale):
        await run_large_transfers(LargeTransfersIn(mint=MINT, wallets=["7" * 44]), rpc)
