"""Per-seat bearer auth over POST /mcp/<short> (TOOL-010, T-03-05-01/02).

Tokens come from ``DESK_GATEWAY_TOKEN_<SHORT>`` only and are compared
with ``hmac.compare_digest`` in a loop over every seat: no match is 401,
a match for another seat is 403, and a path seat with no configured
token fails closed with 503 and no token detail. Only the seat short
name and the status code are ever logged.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import httpx
import pytest
from conftest import (
    HTTP_FORBIDDEN,
    HTTP_METHOD_NOT_ALLOWED,
    HTTP_OK,
    HTTP_SEAT_UNCONFIGURED,
    HTTP_UNAUTHORIZED,
    _refusing_transport,
    rpc_call,
    rpc_call_as,
)

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.replay.clock import WallClock


def _serve_without(short_missing: str, tmp_path: Any) -> Any:
    """Live server with every seat token configured except one."""
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = {short: f"fake_token_{short}" for short in shorts if short != short_missing}
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing_transport))
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        data_dir=tmp_path / "data",
        repo_root=tmp_path,
        tokens=tokens,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    server = create_server(
        config,
        settings=Settings(mode="paper"),
        clock=WallClock(),
        http_client=http_client,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}", tokens


@pytest.fixture()
def unconfigured_gateway(tmp_path: Any) -> Any:
    server, base_url, tokens = _serve_without("journal", tmp_path)
    yield base_url, tokens
    close_server(server)


def test_missing_token_is_401(gateway):  # type: ignore[no-untyped-def]
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/list", None)
    assert status == HTTP_UNAUTHORIZED, body
    assert body["error"]["code"] == "unauthorized"


def test_wrong_token_is_401(gateway):  # type: ignore[no-untyped-def]
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/list", "fake_token_nope")
    assert status == HTTP_UNAUTHORIZED, body
    assert body["error"]["code"] == "unauthorized"


def test_cross_seat_token_is_403(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/list", tokens["scout"])
    assert status == HTTP_FORBIDDEN, body
    assert body["error"]["code"] == "forbidden"


def test_own_seat_token_proceeds(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "scout", "tools/list", tokens["scout"])
    assert status == HTTP_OK, body
    assert body["result"]["tools"]


def test_unconfigured_seat_is_503_without_detail(unconfigured_gateway):  # type: ignore[no-untyped-def]
    base_url, tokens = unconfigured_gateway
    status, body = rpc_call(base_url, "journal", "tools/list", tokens["scout"])
    assert status == HTTP_SEAT_UNCONFIGURED, body
    assert body["error"]["code"] == "seat_unconfigured"
    dumped = json.dumps(body)
    assert not any(value in dumped for value in tokens.values())


def test_get_is_405(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call_as(base_url, "chief", "GET", tokens["chief"])
    assert status == HTTP_METHOD_NOT_ALLOWED, body
