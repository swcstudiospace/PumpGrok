"""RPC discipline for TOOL-002: retry predicate, policy values, decode, redaction.

httpx.MockTransport fixtures only (B13: no respx). WallClock with a tiny
policy keeps retry sleeps in the tens of milliseconds; no test asserts on
elapsed time.
"""

from __future__ import annotations

import random
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx
import pytest
from pydantic import SecretStr

from pumpgrok.core.errors import DataStale
from pumpgrok.core.tool import RetryPolicy
from pumpgrok.replay.clock import WallClock
from pumpgrok.tools.onchain.rpc import RpcClient, RpcError, _SeededWait

TINY = RetryPolicy(attempts=3, base_s=0.01, max_s=0.02)


def _rpc(
    handler: object,
    endpoints: tuple[str, ...] = ("https://rpc.invalid",),
    *,
    retry: RetryPolicy | None = TINY,
    api_key: SecretStr | None = None,
    seed: int = 7,
) -> RpcClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    client = httpx.AsyncClient(transport=transport)
    return RpcClient(
        list(endpoints),
        client,
        WallClock(),
        rng=random.Random(seed),
        retry=retry,
        api_key=api_key,
    )


async def test_4xx_fails_over_without_retry_delay() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(400, json={"error": {"code": -32601, "message": "nope"}})

    rpc = _rpc(handler, endpoints=("https://rpc.invalid/a", "https://rpc.invalid/b"))
    with pytest.raises(RpcError, match="rpc failed method=getFoo endpoints=2"):
        await rpc.call("getFoo", [])
    assert len(calls) == 2  # one attempt per endpoint, no retries


async def test_single_4xx_endpoint_raises_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": -32601, "message": "nope"}})

    rpc = _rpc(handler)
    with pytest.raises(RpcError) as excinfo:
        await rpc.call("getFoo", [])
    assert "rpc.invalid" not in str(excinfo.value)


async def test_500_retries_then_fails_over_in_order() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/a":
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 42})

    rpc = _rpc(handler, endpoints=("https://rpc.invalid/a", "https://rpc.invalid/b"))
    assert await rpc.call("getFoo", []) == 42
    assert [u.rsplit("/", 1)[-1] for u in calls] == ["a", "a", "a", "b"]


async def test_429_retried_per_policy() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(429, json={"error": "slow down"})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "ok"})

    rpc = _rpc(handler)
    assert await rpc.call("getFoo", []) == "ok"
    assert calls == 3


async def test_timeout_retried_then_typed_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("too slow")

    rpc = _rpc(handler, retry=RetryPolicy(attempts=2, base_s=0.01, max_s=0.02))
    with pytest.raises(RpcError, match="rpc failed"):
        await rpc.call("getFoo", [])
    assert calls == 2


async def test_rpc_error_object_fails_over_immediately() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/a":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"code": -32005}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "fine"})

    rpc = _rpc(handler, endpoints=("https://rpc.invalid/a", "https://rpc.invalid/b"))
    assert await rpc.call("getFoo", []) == "fine"
    assert [u.rsplit("/", 1)[-1] for u in calls] == ["a", "b"]


async def test_malformed_body_yields_data_stale() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    rpc = _rpc(handler)
    with pytest.raises(DataStale, match="rpc bad body"):
        await rpc.call("getFoo", [])


async def test_malformed_first_endpoint_fails_over_to_good() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(200, content=b"not json")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "recovered"})

    rpc = _rpc(handler, endpoints=("https://rpc.invalid/a", "https://rpc.invalid/b"))
    assert await rpc.call("getFoo", []) == "recovered"


async def test_api_key_travels_in_header_only() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["header"] = request.headers.get("x-api-key", "")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "ok"})

    rpc = _rpc(handler, api_key=SecretStr("s3cret"))
    assert await rpc.call("getFoo", []) == "ok"
    assert seen["header"] == "s3cret"
    assert "s3cret" not in seen["url"]


async def test_no_key_sends_no_auth_header() -> None:
    seen: dict[str, bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["has_header"] = "x-api-key" in request.headers
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "ok"})

    rpc = _rpc(handler)
    assert await rpc.call("getFoo", []) == "ok"
    assert seen["has_header"] is False


def test_seeded_wait_uses_policy_bounds() -> None:
    wait = _SeededWait(random.Random(0), base=0.5, cap=4.0)
    first = wait(types.SimpleNamespace(attempt_number=1))
    assert 0.5 <= first <= 1.0
    second = wait(types.SimpleNamespace(attempt_number=2))
    assert 1.0 <= second <= 2.0
    late = wait(types.SimpleNamespace(attempt_number=10))
    assert 4.0 <= late <= 8.0
