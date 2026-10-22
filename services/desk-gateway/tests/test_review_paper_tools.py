"""Gateway execution tools are served by the shared PaperAdapter, not the stub (PR 6 r3 #11).

``build_gateway_registry`` used to bind every execution tool to
``NotYetImplementedAdapter``, so authenticated callers got
``not_yet_implemented`` for positions, quotes and every other paper
operation. These tests pin that the gateway answers through the paper
implementation: a read with no ledger history succeeds, and a quote with no
curve source fails closed with the adapter's own refusal, never the stub.
"""

from __future__ import annotations

import json

from conftest import HTTP_OK, rpc_call

WSOL = "So11111111111111111111111111111111111111112"


def _call(base_url, short, token, name, arguments):  # type: ignore[no-untyped-def]
    return rpc_call(
        base_url,
        short,
        "tools/call",
        token,
        {"name": name, "arguments": arguments},
    )


def test_positions_is_served_by_paper_adapter(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    status, body = _call(base_url, "chief", tokens["chief"], "exec_positions", {})
    assert status == HTTP_OK, body
    result = body["result"]
    assert result["isError"] is False, result
    assert result.get("code") is None
    payload = json.loads(result["content"][0]["text"])
    assert payload["positions"] == []


def test_quote_is_not_the_stub(gateway):  # type: ignore[no-untyped-def]
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
    assert result["code"] != "not_yet_implemented"
    assert result["code"] == "no_reserves"
