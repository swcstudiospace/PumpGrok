# Offline frame-capture tests for the read-only transport boundary.
from __future__ import annotations

import traceback

import pytest

from pumpgrok.datafeed.readonly import ReadOnlyBoundary


class CaptureTransport:
    def __init__(self) -> None:
        self.frames: list[tuple[str, dict[str, object]]] = []

    async def send(self, url: str, frame: dict[str, object]) -> object:
        self.frames.append((url, frame))
        return {"result": "fixture response"}


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("logsSubscribe", [{"mentions": ["Program111"]}, {"commitment": "confirmed"}]),
        ("getAccountInfo", ["Account111", {"encoding": "base64"}]),
        (
            "getTransaction",
            ["Signature111", {"encoding": "json", "maxSupportedTransactionVersion": 0}],
        ),
    ],
)
async def test_allowed_rpc_reads_reach_injected_transport(
    method: str, params: list[object]
) -> None:
    transport = CaptureTransport()
    endpoint = "https://rpc.example.invalid"
    boundary = ReadOnlyBoundary(endpoint=endpoint, transport=transport)

    result = await boundary.rpc(method, params)

    assert transport.frames == [(endpoint, {"method": method, "params": params})]
    assert result == {"result": "fixture response"}


@pytest.mark.parametrize("method", ["subscribeNewToken", "subscribeMigration"])
async def test_allowed_portal_subscriptions_reach_injected_transport(method: str) -> None:
    transport = CaptureTransport()
    endpoint = "wss://portal.example.invalid/api/data"
    boundary = ReadOnlyBoundary(endpoint=endpoint, transport=transport)

    result = await boundary.portal(method)

    assert transport.frames == [(endpoint, {"method": method})]
    assert result == {"result": "fixture response"}


@pytest.mark.parametrize(
    "method", ["sendTransaction", "simulateTransaction", "requestAirdrop", "unknownMethod", ""]
)
async def test_other_rpc_methods_are_refused_before_transport(method: str) -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="https://rpc.example.invalid", transport=transport)

    with pytest.raises(ValueError):
        await boundary.rpc(method, [])
    assert transport.frames == []


@pytest.mark.parametrize("method", ["subscribeTokenTrade", "trade", "sendTransaction", ""])
async def test_other_portal_methods_are_refused_before_transport(method: str) -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="wss://portal.example.invalid/api/data", transport=transport)

    with pytest.raises(ValueError):
        await boundary.portal(method)
    assert transport.frames == []


@pytest.mark.parametrize("channel", ["rpc", "portal"])
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:example-secret@rpc.example.invalid",
        "https://user@rpc.example.invalid",
        "https://rpc.example.invalid?api_key=example-secret",
        "https://rpc.example.invalid?token=example-secret",
        "https://rpc.example.invalid?api%5Fkey=example-secret",
        "https://rpc.example.invalid?authorization=example-secret",
        "http://rpc.example.invalid?token=example-secret",
        "wss://portal.example.invalid/api/data?password=example-secret",
    ],
)
async def test_credential_urls_are_refused_and_redacted_before_transport(
    endpoint: str, channel: str
) -> None:
    transport = CaptureTransport()

    with pytest.raises(ValueError) as raised:
        boundary = ReadOnlyBoundary(endpoint=endpoint, transport=transport)
        if channel == "rpc":
            await boundary.rpc("getAccountInfo", ["Account111"])
        else:
            await boundary.portal("subscribeNewToken")
    assert "example-secret" not in str(raised.value)
    assert "user@" not in str(raised.value)
    assert transport.frames == []


async def test_transport_failures_do_not_echo_credentials() -> None:
    class FailingTransport:
        async def send(self, url: str, frame: dict[str, object]) -> object:
            raise RuntimeError("connection failed: token=example-secret")

    boundary = ReadOnlyBoundary(
        endpoint="https://rpc.example.invalid", transport=FailingTransport()
    )
    with pytest.raises(Exception) as raised:
        await boundary.rpc("getAccountInfo", ["Account111"])
    assert "example-secret" not in str(raised.value)
    assert "example-secret" not in "".join(traceback.format_exception(raised.value))


async def test_changed_endpoint_is_checked_again_before_transport() -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="https://rpc.example.invalid", transport=transport)
    boundary.endpoint = "https://rpc.example.invalid?token=example-secret"
    with pytest.raises(ValueError):
        await boundary.rpc("getAccountInfo", ["Account111"])
    assert transport.frames == []


async def test_nonsecret_query_is_allowed() -> None:
    transport = CaptureTransport()
    endpoint = "https://rpc.example.invalid?cluster=mainnet"
    boundary = ReadOnlyBoundary(endpoint=endpoint, transport=transport)
    await boundary.rpc("getAccountInfo", ["Account111"])
    assert transport.frames == [
        (endpoint, {"method": "getAccountInfo", "params": ["Account111"]})
    ]
