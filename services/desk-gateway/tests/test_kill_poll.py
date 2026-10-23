"""The gateway polls the kill sources on a fixed cycle, with no order requests (review finding 9).

The gateway attaches the flatten hook to its risk engine, but nothing calls
``RiskEngine.poll_kill_sources`` unless an order is checked. The owner loop must run its own
periodic poll, so a ``KILL FLATTEN`` on the alert channel closes an open position on an idle
gateway. The channel is a fake: no network, no Telegram.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import httpx
import pytest

from desk_gateway.config import GatewayConfig
from desk_gateway.server import close_server, create_server
from pumpgrok.config.settings import Settings
from pumpgrok.contracts.projection import default_contracts_dir
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import WallClock, format_ts_utc

REPO_ROOT = Path(__file__).resolve().parents[3]
MINT = "So11111111111111111111111111111111111111112"
TICKET = "SOL-20260201-001"
POLL_INTERVAL_S = 0.05
DEADLINE_S = 15.0


class FakeChannel:
    """Alert channel stand-in: hands out queued lines once, then nothing."""

    def __init__(self, lines: list[str]) -> None:
        self.pending = list(lines)
        self.commits = 0

    def poll(self) -> list[str]:
        lines, self.pending = self.pending, []
        return lines

    def commit(self) -> None:
        self.commits += 1


def _refusing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "network disabled in gateway tests"})


def _seed_open_position(ledger: Path) -> None:
    """One open paper position with a ledger mark, so the flatten can value it."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    store = LedgerStore(str(ledger))
    try:
        store.set_meta("initial_equity_lamports", "10000000000")
        store.set_meta("source", "paper")
        now = format_ts_utc(WallClock().now())
        store.append(
            ts_utc=now,
            source="paper",
            correlation_id="seed",
            idempotency_key="seed-pos",
            type="PositionOpened",
            payload={
                "source": "paper",
                "mint": MINT,
                "price_entry": "0.00001",
                "token_units": 3_000_000,
                "cost_basis_lamports": 200_000_000,
                "opened_ts_utc": now,
                "symbol": "TST",
                "creator": "Creator1111111111111111111111111111111111",
                "ticket_id": TICKET,
                "score": "0.8",
            },
        )
        store.append(
            ts_utc=now,
            source="paper",
            correlation_id="seed",
            idempotency_key="seed-mark",
            type="MarkToMarket",
            payload={
                "source": "paper",
                "ts_source": now,
                "cash_lamports": 9_800_000_000,
                "equity_lamports": 10_000_000_000,
                "unrealized_lamports": 0,
                "prices_json": json.dumps(
                    {MINT: {"mtm_lamports": 200_000_000, "venue_fee_lamports": 0, "spot": "1e-5"}}
                ),
            },
        )
    finally:
        store.close()


def _closed_reasons(ledger: Path) -> list[str]:
    store = LedgerStore(str(ledger))
    try:
        rows = store.read(types=["PositionClosed"], limit=None)
        return [str(row["payload"]["reason"]) for row in rows]
    finally:
        store.close()


def test_idle_gateway_flattens_on_alert_kill_flatten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in list(os.environ):
        if name.startswith(("PUMPGROK_", "DESK_GATEWAY_")):
            monkeypatch.delenv(name)
    ledger = tmp_path / "var" / "ledger.sqlite"
    _seed_open_position(ledger)
    channel = FakeChannel(["KILL FLATTEN close all"])
    config = GatewayConfig(
        host="127.0.0.1",
        port=0,
        contracts_dir=default_contracts_dir(),
        data_dir=tmp_path / "var" / "desk",
        repo_root=REPO_ROOT,
        tokens={},
        ledger_path=ledger,
    )
    server = create_server(
        config,
        settings=Settings(mode="paper"),
        clock=WallClock(),
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(_refusing)),
        alert_channel=channel,  # type: ignore[arg-type]
        kill_poll_interval_s=POLL_INTERVAL_S,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # No order request is ever sent: the poll alone must close the position.
        deadline = time.monotonic() + DEADLINE_S
        reasons: list[str] = []
        while time.monotonic() < deadline:
            reasons = _closed_reasons(ledger)
            if reasons:
                break
            time.sleep(0.05)
        assert reasons == ["kill_flatten"], reasons
        assert channel.commits >= 1
    finally:
        task = server.gateway_state.get("kill_poll_task")  # type: ignore[attr-defined]
        close_server(server)
        thread.join(timeout=5)
    # Clean shutdown: the periodic poll task exists and is finished, not left on the loop.
    assert task is not None
    assert task.done()
