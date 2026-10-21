"""Regression (WR-09): an over-long Content-Length digit string is a 400, not a drop.

Python 3.11+ caps int<->str digit conversion (4300 digits), so ``int(value)``
on an unbounded ``[0-9]+`` raises ``ValueError``. ``_declared_length`` must
cap the digit length and convert defensively, returning the existing 400
``bad_length`` path. Auth still precedes the length check: an unauthenticated
over-long request answers 401, never 400.
"""

from __future__ import annotations

import http.client
import json
from typing import Any

from conftest import HTTP_UNAUTHORIZED

HTTP_BAD_REQUEST = 400
LONG_LENGTH = "9" * 4300


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


def test_over_long_content_length_is_400(gateway: Any) -> None:
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", tokens["chief"], [("Content-Length", LONG_LENGTH)])
    assert status == HTTP_BAD_REQUEST, body
    assert body["error"]["code"] == "bad_length"


def test_over_long_length_unauthenticated_is_401_not_400(gateway: Any) -> None:
    base_url, _tokens, _contracts, _reg, _manifests = gateway
    status, body = _raw_post(base_url, "chief", "wrong-token", [("Content-Length", LONG_LENGTH)])
    assert status == HTTP_UNAUTHORIZED, body
    assert body["error"]["code"] == "unauthorized"
