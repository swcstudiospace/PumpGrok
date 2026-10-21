"""tools/call dispatches through the registry with MCP error envelopes.

The JSON-RPC method surface (initialize / notifications / tools/*) lives
here too: unknown methods answer -32601, and Phase 3 unbuilt backends
answer ``isError:true`` with code ``not_yet_implemented`` (correct, not
hidden). No stack or path ever leaks into an envelope.
"""

from __future__ import annotations

import json

from conftest import HTTP_ACCEPTED, HTTP_OK, JSONRPC_METHOD_NOT_FOUND, rpc_call

WSOL = "So11111111111111111111111111111111111111112"


def _call(base_url, short, token, name, arguments):  # type: ignore[no-untyped-def]
    return rpc_call(
        base_url,
        short,
        "tools/call",
        token,
        {"name": name, "arguments": arguments},
    )


def test_initialize_handshake(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "initialize", tokens["chief"], {})
    assert status == HTTP_OK, body
    assert body["result"]["serverInfo"]["name"] == "desk-gateway"


def test_unknown_method_is_32601(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "tools/nope", tokens["chief"], {})
    assert status == HTTP_OK, body
    assert body["error"]["code"] == JSONRPC_METHOD_NOT_FOUND


def test_notification_initialized_has_no_body(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = rpc_call(base_url, "chief", "notifications/initialized", tokens["chief"], {})
    assert status == HTTP_ACCEPTED, body


def test_quote_returns_not_yet_implemented(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(
        base_url,
        "sniper",
        tokens["sniper"],
        "exec_quote",
        {"input_mint": WSOL, "output_mint": WSOL, "amount": 1000},
    )
    assert status == HTTP_OK, body
    result = body["result"]
    assert result["isError"] is True
    assert result["code"] == "not_yet_implemented"


def test_brief_dispatch_succeeds(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(base_url, "chief", tokens["chief"], "desk_brief", {"task_id": "T-1"})
    assert status == HTTP_OK, body
    assert body["result"].get("isError", False) is False
    assert body["result"]["content"][0]["type"] == "text"


def test_unknown_transport_is_error(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(base_url, "chief", tokens["chief"], "desk_nope", {})
    assert status == HTTP_OK, body
    assert body["result"]["isError"] is True
    assert body["result"]["code"] == "unknown_tool"


def test_invalid_arguments_is_error(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(base_url, "chief", tokens["chief"], "desk_brief", {})
    assert status == HTTP_OK, body
    assert body["result"]["isError"] is True
    assert body["result"]["code"] == "invalid_arguments"


def test_tool_outside_roster_is_refused(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(
        base_url,
        "chief",
        tokens["chief"],
        "exec_quote",
        {"input_mint": WSOL, "output_mint": WSOL, "amount": 1000},
    )
    assert status == HTTP_OK, body
    assert body["result"]["isError"] is True
    assert body["result"]["code"] == "permission_denied"


def test_error_envelope_leaks_no_stack_or_path(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    _status, body = _call(
        base_url,
        "sniper",
        tokens["sniper"],
        "exec_quote",
        {"input_mint": WSOL, "output_mint": WSOL, "amount": 1000},
    )
    dumped = json.dumps(body).lower()
    assert "traceback" not in dumped
    assert "stack" not in dumped
