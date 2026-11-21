"""Shared live-HTTP fixtures for the desk-gateway suite (TOOL-010).

The suite drives a real ``ThreadingHTTPServer`` on 127.0.0.1 over an
ephemeral port through a plain ``httpx`` client, so the wire (auth codes,
JSON-RPC errors, MCP envelopes) is what the tests pin. Registry and
tokens are built per module in a tmp data dir; no live network is ever
touched (the RPC client answers through ``httpx.MockTransport``).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.replay.clock import WallClock

HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_SEAT_UNCONFIGURED = 503
JSONRPC_METHOD_NOT_FOUND = -32601


def _refusing_transport(request: httpx.Request) -> httpx.Response:
    """Safety net: no gateway test may reach a real network."""
    return httpx.Response(500, json={"error": "network disabled in gateway tests"})


def _rpc_body(method: str, params: dict[str, Any] | None) -> bytes:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    return json.dumps(payload).encode()


def _exchange(
    base_url: str, short: str, http_method: str, token: str | None, body: bytes
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    response = httpx.request(http_method, f"{base_url}/mcp/{short}", content=body, headers=headers)
    raw = response.text
    try:
        return response.status_code, json.loads(raw or "null")
    except json.JSONDecodeError:
        return response.status_code, {"raw": raw}


def rpc_call(
    base_url: str,
    short: str,
    method: str,
    token: str | None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """POST one JSON-RPC call; return (status, decoded body)."""
    return _exchange(base_url, short, "POST", token, _rpc_body(method, params))


def rpc_call_as(base_url: str, short: str, http_method: str, token: str | None) -> tuple[int, Any]:
    """Send a tools/list envelope with another HTTP verb (verb-gating tests)."""
    return _exchange(base_url, short, http_method, token, _rpc_body("tools/list", None))


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Live server with per-seat placeholder tokens and a tmp data dir."""
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = {short: f"fake_token_{short}" for short in shorts}
    data_dir = tmp_path_factory.mktemp("gateway-data")
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing_transport))
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        data_dir=data_dir,
        repo_root=Path(__file__).resolve().parents[3],
        tokens=tokens,
        ledger_path=data_dir / "ledger.sqlite",
    )
    server = create_server(
        config,
        settings=Settings(mode="paper"),
        clock=WallClock(),
        http_client=http_client,
    )
    registry = server.gateway_state["registry"]  # type: ignore[attr-defined]
    manifests = server.gateway_state["manifests"]  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", tokens, contracts_dir, registry, manifests
    finally:
        close_server(server)
