"""HOST-04: ledger_status comes from the tick verification, never a constant."""

from __future__ import annotations

import asyncio
import json
import urllib.request

from pumpgrok.replay.clock import FixtureClock
from pumpgrok.supervisor.health_server import HostedHealthServer


def _fetch(port: int) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/readyz", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8"))


async def _status_for(ledger_status: str) -> str:
    clock = FixtureClock(start=1_700_000_000.0)
    server = HostedHealthServer(
        clock,
        lambda: {"halted": False, "ledger_status": ledger_status},
        lambda: ledger_status == "CONSISTENT",
    )
    port = await server.start("127.0.0.1", 0)
    try:
        body = await asyncio.to_thread(_fetch, port)
        return str(body["ledger_status"])
    finally:
        await server.stop()


def test_consistent_reports_consistent() -> None:
    assert asyncio.run(_status_for("CONSISTENT")) == "CONSISTENT"


def test_corrupt_reports_non_consistent() -> None:
    assert asyncio.run(_status_for("INCONSISTENT")) == "INCONSISTENT"
