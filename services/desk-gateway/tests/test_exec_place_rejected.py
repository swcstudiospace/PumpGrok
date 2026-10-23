"""A rejected paper order is an error on the wire, never a success result (TOOL-004, G6).

``exec.place`` reports a refused order as ``status: rejected`` in its payload. The gateway
must surface that as ``isError: true`` with the refusal reason as ``code``, so an MCP
client cannot read a refused order as a placed one.
"""

from __future__ import annotations

import json

from conftest import HTTP_OK, rpc_call

WSOL = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
DECISION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
APPROVAL_ID = "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_rejected_exec_place_is_an_error_result(gateway):  # type: ignore[no-untyped-def]
    base_url, tokens, _contracts, _reg, _manifests = gateway
    arguments = {
        "ticket_id": TICKET,
        "mint": WSOL,
        "side": "buy",
        "decision_id": DECISION_ID,
        "size_lamports": 1000,
        "max_slippage_bps": 50,
        "approval_id": APPROVAL_ID,
    }
    status, body = rpc_call(
        base_url,
        "sniper",
        "tools/call",
        tokens["sniper"],
        {"name": "exec_place", "arguments": arguments},
    )
    assert status == HTTP_OK, body
    result = body["result"]
    payload = json.loads(result["content"][0]["text"])
    assert payload["status"] == "rejected", payload
    assert result["isError"] is True, result
    assert result["code"] == payload["reason"]
    assert result["code"]
