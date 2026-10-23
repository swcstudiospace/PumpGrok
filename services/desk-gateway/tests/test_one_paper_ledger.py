"""One paper ledger: the gateway writes the ledger ``pumpgrok report --daily`` reads.

The CLI and replay open ``var/ledger.sqlite`` (relative to the working directory). An order
placed through the gateway must land in that same file, or the desk has two ledgers and the
daily report misses trades. The order here is an ``exec_place`` with an unknown approval: the
adapter refuses it and records an ``OrderRejected`` row, which the daily report counts.
"""

from __future__ import annotations

import datetime as dt
import threading
from pathlib import Path

import httpx
import pytest
from conftest import HTTP_OK, _refusing_transport, rpc_call

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.cli import main as cli_main
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import default_contracts_dir, short_to_seat
from pumpgrok.replay.clock import WallClock

WSOL = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
DECISION_ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
APPROVAL_ID = "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"


def test_gateway_order_is_in_the_ledger_the_cli_report_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The working directory is the desk root: var/ledger.sqlite and var/desk/ are under it.
    monkeypatch.chdir(tmp_path)
    contracts_dir = default_contracts_dir()
    shorts = sorted(short_to_seat(contracts_dir).keys())
    tokens = {short: f"fake_token_{short}" for short in shorts}
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=contracts_dir,
        data_dir=tmp_path / "var" / "desk",
        repo_root=Path(__file__).resolve().parents[3],
        tokens=tokens,
    )
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(_refusing_transport))
    server = create_server(
        config,
        settings=Settings(mode="paper"),
        clock=WallClock(),
        http_client=http_client,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        status, body = rpc_call(
            f"http://{host}:{port}",
            "sniper",
            "tools/call",
            tokens["sniper"],
            {
                "name": "exec_place",
                "arguments": {
                    "ticket_id": TICKET,
                    "mint": WSOL,
                    "side": "buy",
                    "decision_id": DECISION_ID,
                    "size_lamports": 1000,
                    "max_slippage_bps": 50,
                    "approval_id": APPROVAL_ID,
                },
            },
        )
    finally:
        close_server(server)
        thread.join(timeout=5)
    assert status == HTTP_OK, body
    assert body["result"]["isError"] is True

    day = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    assert cli_main(["report", "--daily"]) == 0
    report = capsys.readouterr().out
    assert day in report
    assert "approval_missing" in report, report
