"""HTTP hardening (raw wire): socket timeout, non-ASCII bearer, deep JSON nesting.

Requests go over a raw socket so the exact bytes on the wire are under test.
The idle-connection case shortens the handler's per-socket timeout through the
class attribute the stdlib reads on every accepted connection, so it runs fast.
Every request asks the server to close, so the response can be read to EOF.
"""

from __future__ import annotations

import json
import socket
import time
from typing import Any

import pytest
from conftest import HTTP_OK, HTTP_UNAUTHORIZED

from desk_gateway.server import _Handler

HTTP_BAD_REQUEST = 400
JSONRPC_PARSE_ERROR = -32700
IDLE_TIMEOUT_S = 0.5
CLIENT_SOCKET_TIMEOUT_S = 5.0
DEEP_NESTING_DEPTH = 100_000


def _split_host_port(base_url: str) -> tuple[str, int]:
    host, port = base_url.removeprefix("http://").rsplit(":", 1)
    return host, int(port)


def _post_request(short: str, body: bytes, authorization: bytes | None) -> bytes:
    lines = [
        f"POST /mcp/{short} HTTP/1.1".encode(),
        b"Host: localhost",
        b"Content-Type: application/json",
        f"Content-Length: {len(body)}".encode(),
        b"Connection: close",
    ]
    if authorization is not None:
        lines.append(b"Authorization: " + authorization)
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def _rpc_bytes(method: str) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": 1, "method": method}).encode()


def _read_to_eof(sock: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _raw_round_trip(base_url: str, request: bytes) -> bytes:
    host, port = _split_host_port(base_url)
    with socket.create_connection((host, port), timeout=CLIENT_SOCKET_TIMEOUT_S) as sock:
        sock.sendall(request)
        return _read_to_eof(sock)


def _parse_response(raw: bytes) -> tuple[int, Any]:
    assert raw.startswith(b"HTTP/1."), f"no HTTP response, connection dropped: {raw!r}"
    head, _, body = raw.partition(b"\r\n\r\n")
    status = int(head.split(b" ", 2)[1])
    return status, json.loads(body or b"null")


def test_idle_connection_is_closed_within_handler_timeout(
    gateway: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    monkeypatch.setattr(_Handler, "timeout", IDLE_TIMEOUT_S)
    host, port = _split_host_port(base_url)
    with socket.create_connection((host, port), timeout=CLIENT_SOCKET_TIMEOUT_S) as sock:
        started = time.monotonic()
        try:
            received = sock.recv(1)
        except TimeoutError:
            pytest.fail("idle connection was not closed by the server within the timeout")
        elapsed = time.monotonic() - started
    assert received == b"", "server must close the idle socket without sending anything"
    assert elapsed >= IDLE_TIMEOUT_S * 0.8, f"closed too early: {elapsed:.3f}s"
    assert elapsed < CLIENT_SOCKET_TIMEOUT_S, f"closed too late: {elapsed:.3f}s"


def test_non_ascii_bearer_token_is_401_not_dropped(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    body = _rpc_bytes("tools/list")
    non_ascii = ("Bearer fake_token_chief\u00e9").encode()
    status, payload = _parse_response(
        _raw_round_trip(base_url, _post_request("chief", body, non_ascii))
    )
    assert status == HTTP_UNAUTHORIZED, payload
    assert payload["error"]["code"] == "unauthorized"

    valid = f"Bearer {tokens['chief']}".encode()
    status, payload = _parse_response(
        _raw_round_trip(base_url, _post_request("chief", body, valid))
    )
    assert status == HTTP_OK, payload
    assert "tools" in payload["result"]


def test_deeply_nested_json_is_400_parse_error(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    nested = b"[" * DEEP_NESTING_DEPTH + b"]" * DEEP_NESTING_DEPTH
    authorization = f"Bearer {tokens['chief']}".encode()
    raw = _raw_round_trip(base_url, _post_request("chief", nested, authorization))
    status, payload = _parse_response(raw)
    assert status == HTTP_BAD_REQUEST, payload
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] is None
    assert payload["error"]["code"] == JSONRPC_PARSE_ERROR
