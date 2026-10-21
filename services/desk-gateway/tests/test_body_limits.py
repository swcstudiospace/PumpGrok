"""Body bounds (WR-04): auth first, 400 on a malformed Content-Length, 413 over the cap.

Requests go over a raw ``http.client`` connection so the declared
Content-Length is exactly what the wire carries. Error cases send no body:
the server must answer from the headers alone, never block reading a body
it has already decided to refuse.
"""

from __future__ import annotations

import http.client
import json
from typing import Any

from conftest import HTTP_FORBIDDEN, HTTP_OK, HTTP_UNAUTHORIZED

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_TOO_LARGE = 413
MAX_BODY_BYTES = 1 << 20
OVERSIZE = str(MAX_BODY_BYTES + 1)


def _raw_post(
    base_url: str,
    short: str,
    token: str | None,
    headers: list[tuple[str, str]],
) -> tuple[int, Any]:
    host, port = base_url.removeprefix("http://").rsplit(":", 1)
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    try:
        conn.putrequest("POST", f"/mcp/{short}")
        conn.putheader("Content-Type", "application/json")
        if token is not None:
            conn.putheader("Authorization", f"Bearer {token}")
        for name, value in headers:
            conn.putheader(name, value)
        conn.endheaders()
        response = conn.getresponse()
        return response.status, json.loads(response.read() or b"null")
    finally:
        conn.close()


def test_non_integer_content_length_is_400(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["chief"], [("Content-Length", "abc")])
    assert status == HTTP_BAD_REQUEST, body
    assert body["error"]["code"] == "bad_length"


def test_negative_content_length_is_400(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["chief"], [("Content-Length", "-1")])
    assert status == HTTP_BAD_REQUEST, body
    assert body["error"]["code"] == "bad_length"


def test_empty_content_length_is_400(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["chief"], [("Content-Length", "")])
    assert status == HTTP_BAD_REQUEST, body
    assert body["error"]["code"] == "bad_length"


def test_duplicate_content_length_is_400(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(
        base_url,
        "chief",
        tokens["chief"],
        [("Content-Length", "2"), ("Content-Length", "2")],
    )
    assert status == HTTP_BAD_REQUEST, body
    assert body["error"]["code"] == "bad_length"


def test_oversize_authenticated_is_413_without_reading(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["chief"], [("Content-Length", OVERSIZE)])
    assert status == HTTP_TOO_LARGE, body
    assert body["error"]["code"] == "body_too_large"


def test_oversize_unauthenticated_is_401_not_413(gateway: Any) -> None:
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", None, [("Content-Length", OVERSIZE)])
    assert status == HTTP_UNAUTHORIZED, body
    assert body["error"]["code"] == "unauthorized"


def test_malformed_length_unauthenticated_is_401_not_400(gateway: Any) -> None:
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", None, [("Content-Length", "abc")])
    assert status == HTTP_UNAUTHORIZED, body
    assert body["error"]["code"] == "unauthorized"


def test_oversize_cross_seat_is_403(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["scout"], [("Content-Length", OVERSIZE)])
    assert status == HTTP_FORBIDDEN, body
    assert body["error"]["code"] == "forbidden"


def test_unknown_seat_stays_404(gateway: Any) -> None:
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "nope-seat", None, [("Content-Length", OVERSIZE)])
    assert status == HTTP_NOT_FOUND, body
    assert body["error"]["code"] == "unknown_seat"


def test_valid_length_request_is_still_served(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    host, port = base_url.removeprefix("http://").rsplit(":", 1)
    conn = http.client.HTTPConnection(host, int(port), timeout=10)
    try:
        conn.request(
            "POST",
            "/mcp/chief",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {tokens['chief']}",
            },
        )
        response = conn.getresponse()
        body = json.loads(response.read())
    finally:
        conn.close()
    assert response.status == HTTP_OK, body
    assert body["result"]["tools"]
