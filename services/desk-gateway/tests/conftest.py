"""Shared live-HTTP fixtures for the desk-gateway suite (TOOL-010).

The suite drives a real ``ThreadingHTTPServer`` on 127.0.0.1 over an
ephemeral port with stdlib ``urllib`` only, so the wire (auth codes,
JSON-RPC errors, MCP envelopes) is what the tests pin. Registry and
tokens are built per module in a tmp data dir; no live network is ever
touched (the RPC client answers through ``httpx.MockTransport``).
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import httpx
import pytest

from desk_gateway.server import close_server, create_server
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.replay.clock import WallClock


def _refusing_transport(request: httpx.Request) -> httpx.Response:
    """Safety net: no gateway test may reach a real network."""
    return httpx.Response(500, json={"error": "network disabled in gateway tests"})


def rpc_call(
    base_url: str,
    short: str,
    method: str,
    token: str | None,
    params: dict[str, Any] | None = None,
    *,
    http_method: str = "POST",
) -> tuple[int, Any]:
    """POST one JSON-RPC call; return (status, decoded body)."""
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        payload["params"] = params
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url}/mcp/{short}",
        data=json.dumps(payload).encode(),
        method=http_method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request) as response:
            status = response.status
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw or "null")
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    try:
        return status, json.loads(raw or "null")
    except json.JSONDecodeError:
        return status, {"raw": raw}


@pytest.fixture(scope="module")
def gateway(tmp_path_factory: pytest.TempPathFactory) -> Any:
    """Live server with per-seat placeholder tokens and a tmp data dir."""
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = {short: f"fake_token_{short}" for short in shorts}
    data_dir = tmp_path_factory.mktemp("gateway-data")
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing_transport))
    server = create_server(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        tokens=tokens,
        data_dir=data_dir,
        repo_root=Path(__file__).resolve().parents[3],
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
