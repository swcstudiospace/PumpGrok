"""The gateway binds the operator's loaded settings, not hardcoded defaults (G3).

An operator overlay (``PUMPGROK_CONFIG``) that tightens the risk budget must be the budget the
gateway enforces. ``risk.check_limits`` reports the budget the gateway registry was built with,
so a tightened value there proves the overlay reached the gateway.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest
from conftest import HTTP_OK, _refusing_transport, rpc_call

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.config.settings import load_settings
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.replay.clock import WallClock

WSOL = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
OVERLAY = """
[risk]
max_trade_fraction = "0.001"
max_open_positions = 1
"""


@pytest.fixture
def overlay_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    overlay = tmp_path / "operator.toml"
    overlay.write_text(OVERLAY, encoding="utf-8")
    monkeypatch.setenv("PUMPGROK_CONFIG", str(overlay))
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = {short: f"fake_token_{short}" for short in shorts}
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        data_dir=tmp_path / "desk",
        repo_root=Path(__file__).resolve().parents[3],
        tokens=tokens,
        ledger_path=tmp_path / "ledger.sqlite",
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing_transport))
    server = create_server(
        config,
        settings=load_settings(),
        clock=WallClock(),
        http_client=http_client,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}", tokens
    finally:
        close_server(server)
        thread.join(timeout=5)


def test_overlay_budget_reaches_gateway_risk_budget(overlay_server: Any) -> None:
    base_url, tokens = overlay_server
    status, body = rpc_call(
        base_url,
        "chief",
        "tools/call",
        tokens["chief"],
        {
            "name": "risk_check_limits",
            "arguments": {
                "ticket_id": TICKET,
                "mint": WSOL,
                "side": "sell",
                "size_lamports": 1000,
            },
        },
    )
    assert status == HTTP_OK, body
    result = body["result"]
    assert result["isError"] is False, result
    limits = json.loads(result["content"][0]["text"])["limits"]
    assert limits["max_trade_fraction"] == "0.001"
