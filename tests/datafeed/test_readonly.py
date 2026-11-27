"""Readonly allowlist: only the five methods reachable (MKT-09 first half).

Also: offline frame-capture tests for the read-only transport boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pumpgrok.datafeed.readonly import (
    ALLOWED_METHODS,
    ReadOnlyBoundary,
    ReadonlyError,
    check_method,
    guarded_call,
)
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.live_paper import build_live_paper


def test_five_method_set() -> None:
    assert (
        frozenset(
            {
                "getAccountInfo",
                "logsSubscribe",
                "getTransaction",
                "subscribeNewToken",
                "subscribeMigration",
            }
        )
        == ALLOWED_METHODS
    )


def test_send_transaction_refused_before_call() -> None:
    called: list = []
    with pytest.raises(ReadonlyError, match="sendTransaction"):
        guarded_call("sendTransaction", lambda: called.append(True))
    assert called == []


def test_write_method_refused() -> None:
    with pytest.raises(ReadonlyError):
        check_method("getSignaturesForAddress-driven writes")


def test_allowed_pass() -> None:
    check_method("getAccountInfo")


@pytest.mark.parametrize(
    "method",
    [
        "sendTransaction",
        "signTransaction",
        "getSignaturesForAddress",
        "requestAirdrop",
        "subscribeAccount",
    ],
)
def test_write_methods_refused(method: str) -> None:
    """Every non-allowlisted RPC or portal method is refused by name."""
    with pytest.raises(ReadonlyError):
        check_method(method)


@pytest.mark.parametrize(
    "method",
    [
        "getAccountInfo",
        "logsSubscribe",
        "getTransaction",
        "subscribeNewToken",
        "subscribeMigration",
    ],
)
def test_allowlisted_methods_pass(method: str) -> None:
    check_method(method)


def test_root_feed_call_reaches_only_allowlisted(tmp_path: Path) -> None:
    """The live-paper root exposes only the five allowlisted methods (SC 10)."""

    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:

        async def _place(request):  # pragma: no cover - never called here
            raise AssertionError("feed_call must not place")

        desk = build_live_paper(
            mode="paper",
            store=store,
            clock=FixtureClock(0.0),
            place=_place,
            params={"momentum_breakout": {"breakout_bps": 100}},
        )
        seen: list[str] = []

        def _record(name: str) -> None:
            seen.append(name)

        assert desk.feed_call("getAccountInfo", _record, "acct") is None
        assert seen == ["acct"]
        assert desk.allowed_methods == ALLOWED_METHODS
        with pytest.raises(ReadonlyError):
            desk.feed_call("sendTransaction", lambda: seen.append("sent"))
        assert seen == ["acct"]
    finally:
        store.close()


# --- transport boundary tests ---

import traceback  # noqa: E402


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

    assert len(transport.frames) == 1
    url, frame = transport.frames[0]
    assert url == endpoint
    assert frame["jsonrpc"] == "2.0"
    assert type(frame["id"]) in (int, str)
    assert frame["method"] == method
    assert frame["params"] == params
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
    boundary = ReadOnlyBoundary(
        endpoint="wss://portal.example.invalid/api/data", transport=transport
    )

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
        "https://rpc.example.invalid?accessKey=example-secret",
        "https://rpc.example.invalid?access%4Bey=example-secret",
        "https://rpc.example.invalid?%61ccess%4bey=example-secret",
        "https://rpc.example.invalid?authorization=example-secret",
        "https://rpc.example.invalid?signature=example-secret",
        "https://rpc.example.invalid?sig=example-secret",
        "https://rpc.example.invalid?Sig=example-secret",
        "https://rpc.example.invalid?X-Amz-Signature=example-secret",
        "https://rpc.example.invalid?cluster=devnet&sig=example-secret",
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


async def test_queries_are_refused_even_when_not_recognized_as_secrets() -> None:
    transport = CaptureTransport()
    with pytest.raises(ValueError):
        ReadOnlyBoundary(
            endpoint="https://rpc.example.invalid?cluster=mainnet", transport=transport
        )
    assert transport.frames == []


async def test_rpc_request_ids_are_distinct() -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="https://rpc.example.invalid", transport=transport)
    await boundary.rpc("getAccountInfo", ["Account111"])
    await boundary.rpc("getAccountInfo", ["Account222"])
    assert transport.frames[0][1]["id"] != transport.frames[1][1]["id"]


@pytest.mark.parametrize("channel", ["rpc", "portal"])
@pytest.mark.parametrize(
    "query",
    [
        "signature=example-secret",  # pragma: allowlist secret: example signature placeholder
        "sig=example-secret",
        "X-Amz-Signature=example-secret",  # pragma: allowlist secret: example signature placeholder
    ],
)
async def test_signed_urls_swapped_in_after_construction_are_refused(
    query: str, channel: str
) -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="https://rpc.example.invalid", transport=transport)
    boundary.endpoint = f"https://rpc.example.invalid?{query}"

    with pytest.raises(ValueError) as raised:
        if channel == "rpc":
            await boundary.rpc("getAccountInfo", ["Account111"])
        else:
            await boundary.portal("subscribeNewToken")
    assert "example-secret" not in str(raised.value)
    assert transport.frames == []


async def test_every_rpc_frame_carries_the_complete_jsonrpc_envelope() -> None:
    transport = CaptureTransport()
    boundary = ReadOnlyBoundary(endpoint="https://rpc.example.invalid", transport=transport)
    params_sent: list[list[object]] = [["Account111"], ["Account222"], ["Account333"]]
    for params in params_sent:
        await boundary.rpc("getAccountInfo", params)

    assert len(transport.frames) == len(params_sent)
    for (_, frame), params in zip(transport.frames, params_sent, strict=True):
        assert set(frame) == {"jsonrpc", "id", "method", "params"}
        assert frame["jsonrpc"] == "2.0"
        assert frame["method"] == "getAccountInfo"
        assert frame["params"] == params
    ids = [frame["id"] for _, frame in transport.frames]
    assert len(set(ids)) == len(ids)
